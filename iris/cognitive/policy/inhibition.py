from __future__ import annotations

from iris.cognitive.cycle.models import PolicyResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.cognitive.workspace.frame import WorkspaceFrame
from iris.contracts.policy import ActionPreference, PolicyConstraint

_HIGH_AROUSAL_THRESHOLD = 0.75
_NEGATIVE_VALENCE_THRESHOLD = -0.55
_LOW_FAMILIARITY_THRESHOLD = 0.2
_SELF_HARM_OR_ABUSE_TERMS = (
    "abuse",
    "abused",
    "kill myself",
    "self harm",
    "self-harm",
    "suicide",
    "虐待",
    "自傷",
    "死にたい",
)


class PolicyInhibitionStep(PipelineStep[PolicyResult]):
    name = "policy_inhibition"

    async def run(self, frame: WorkspaceFrame) -> PolicyResult:
        constraints: list[PolicyConstraint] = []
        preferences: list[ActionPreference] = []

        constraints.extend(_constraints_for_candidate_actions(frame))
        constraints.extend(_constraints_for_affect(frame))
        constraints.extend(_constraints_for_relationship(frame))
        constraints.extend(_constraints_for_input_notes(frame))

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
    if relationship.user_label is None or relationship.familiarity >= _LOW_FAMILIARITY_THRESHOLD:
        return ()
    return (
        PolicyConstraint(
            name="low_familiarity",
            reason="relationship familiarity is low",
            prompt_instruction="avoid over-familiarity",
        ),
    )


def _constraints_for_input_notes(frame: WorkspaceFrame) -> tuple[PolicyConstraint, ...]:
    if frame.interpreted_input is None or frame.interpreted_input.text is None:
        return ()
    text = frame.interpreted_input.text.casefold()
    if not any(term in text for term in _SELF_HARM_OR_ABUSE_TERMS):
        return ()
    return (
        PolicyConstraint(
            name="sensitive_safety_context",
            reason="input mentions self-harm or abuse-related content; safety gate remains authoritative",
            prompt_instruction="avoid escalating beyond the safety layer",
        ),
    )


def _summarize_constraints(constraints: list[PolicyConstraint]) -> str | None:
    if not constraints:
        return None
    return "; ".join(item.name for item in constraints)
