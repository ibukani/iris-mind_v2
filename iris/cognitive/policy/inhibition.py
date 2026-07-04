# Copyright 2025 Iris Mind
"""安全性制約のためのポリシー抑制パイプラインステップ。"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from iris.cognitive.cycle.models import PolicyResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.contracts.policy import ActionPreference, PolicyConstraint
from iris.contracts.safety import SafetyResponseDirective

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import WorkspaceFrame
    from iris.contracts.safety import SafetyContext

_HIGH_AROUSAL_THRESHOLD = 0.75
_NEGATIVE_VALENCE_THRESHOLD = -0.55
_LOW_FAMILIARITY_THRESHOLD = 0.2


class PolicyInhibitionStep(PipelineStep[PolicyResult]):
    """フレームからポリシー制約とアクション優先度を評価するパイプラインステップ。"""

    name = "policy_inhibition"

    @override
    async def run(self, frame: WorkspaceFrame) -> PolicyResult:
        """制約と優先度を評価し、ポリシー結果を返す。

        Returns:
            PolicyResult: 評価された制約とアクション優先度を含む結果。
        """
        constraints: list[PolicyConstraint] = []
        preferences: list[ActionPreference] = []

        constraints.extend(_constraints_for_candidate_actions(frame))
        constraints.extend(_constraints_for_affect(frame))
        constraints.extend(_constraints_for_relationship(frame))
        constraints.extend(_constraints_for_safety_contexts(frame))

        if any(item.name == "calm_response" for item in constraints):
            preferences.append(
                ActionPreference(
                    name="prefer_calm_response",
                    reason="high arousal and negative valence",
                    priority_delta=1,
                )
            )

        return PolicyResult(
            step_name=self.name,
            status=StepStatus.OK,
            constraints=tuple(constraints),
            action_preferences=tuple(preferences),
            response_allowed=not any(item.blocks_response for item in constraints),
            policy_summary=_summarize_constraints(constraints),
        )


def _constraints_for_candidate_actions(frame: WorkspaceFrame) -> tuple[PolicyConstraint, ...]:
    constraints: list[PolicyConstraint] = []
    for plan in frame.candidate_action_plans:
        if plan.should_respond and not (plan.candidate_text or "").strip():
            constraints.append(
                PolicyConstraint(
                    name="empty_response_candidate",
                    reason="candidate action plan requested a response without text",
                    prompt_instruction="avoid sending an empty response",
                    blocks_response=True,
                )
            )
            break
    return tuple(constraints)


def _constraints_for_affect(frame: WorkspaceFrame) -> tuple[PolicyConstraint, ...]:
    affect = frame.affect
    if affect.arousal < _HIGH_AROUSAL_THRESHOLD or affect.valence > _NEGATIVE_VALENCE_THRESHOLD:
        return ()
    return (
        PolicyConstraint(
            name="calm_response",
            reason="high arousal with negative valence",
            prompt_instruction="keep tone calm",
        ),
    )


def _constraints_for_relationship(frame: WorkspaceFrame) -> tuple[PolicyConstraint, ...]:
    relationship = frame.relationship
    if relationship.actor_label is None or relationship.familiarity >= _LOW_FAMILIARITY_THRESHOLD:
        return ()
    return (
        PolicyConstraint(
            name="low_familiarity",
            reason="relationship familiarity is low",
            prompt_instruction="avoid over-familiarity",
        ),
    )


def _constraints_for_safety_contexts(frame: WorkspaceFrame) -> tuple[PolicyConstraint, ...]:
    return tuple(_constraint_for_safety_context(context) for context in frame.safety_contexts)


def _constraint_for_safety_context(context: SafetyContext) -> PolicyConstraint:
    directive = context.directive
    if directive is SafetyResponseDirective.ALLOW_SUPPORT:
        return PolicyConstraint(
            name="sensitive_safety_context",
            reason=_safety_reason(context),
            prompt_instruction=(
                "respond supportively, avoid actionable dangerous guidance, "
                "and keep the safety layer authoritative"
            ),
            blocks_response=False,
            safety_context=context,
        )
    if directive is SafetyResponseDirective.SAFE_REDIRECT:
        return PolicyConstraint(
            name="high_risk_safe_redirect_required",
            reason=_safety_reason(context),
            prompt_instruction=(
                "do not answer directly; use the deterministic safe redirect response"
            ),
            blocks_response=True,
            safety_context=context,
        )
    if directive is SafetyResponseDirective.REFUSE:
        return PolicyConstraint(
            name="high_risk_refusal_required",
            reason=_safety_reason(context),
            prompt_instruction="do not answer directly; use the deterministic refusal response",
            blocks_response=True,
            safety_context=context,
        )
    return PolicyConstraint(
        name="high_risk_block_required",
        reason=_safety_reason(context),
        prompt_instruction="do not produce a user-visible response for this context",
        blocks_response=True,
        safety_context=context,
    )


def _safety_reason(context: SafetyContext) -> str:
    reason_codes = ", ".join(reason.code for reason in context.reasons)
    return (
        f"safety_context category={context.category.value} "
        f"severity={context.severity.value} directive={context.directive.value} "
        f"confidence={context.confidence:.2f} reasons={reason_codes}"
    )


def _summarize_constraints(constraints: list[PolicyConstraint]) -> str | None:
    if not constraints:
        return None
    return "; ".join(item.name for item in constraints)
