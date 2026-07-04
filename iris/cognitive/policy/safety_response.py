"""高リスク文脈に対する決定論的な安全応答ステップ。"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from iris.cognitive.cycle.models import ActionSelectionResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.contracts.actions import ActionPlan
from iris.contracts.safety import SafetyContextCategory, SafetyResponseDirective

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import WorkspaceFrame
    from iris.contracts.safety import SafetyContext

_SAFE_RESPONSE_PRIORITY = 1_000


class SafetyResponsePolicyStep(PipelineStep[ActionSelectionResult]):
    """safe redirect / refusal directive を ActionPlan に変換するステップ。"""

    name = "safety_response_policy"

    @override
    async def run(self, frame: WorkspaceFrame) -> ActionSelectionResult:
        """高リスク directive がある場合に決定論的な安全応答を返す。

        Returns:
            安全応答 ActionPlan、または該当なしの SKIPPED 結果。
        """
        context = _first_blocking_context(frame)
        if context is None:
            return ActionSelectionResult(
                step_name=self.name,
                status=StepStatus.SKIPPED,
                reason="no safe response directive",
            )
        plan = ActionPlan(
            turn_intent=_turn_intent(context),
            candidate_text=_response_text(context),
            should_respond=True,
            priority=_SAFE_RESPONSE_PRIORITY,
            interruptible=False,
        )
        return ActionSelectionResult(
            step_name=self.name,
            status=StepStatus.OK,
            action_plans=(plan,),
        )


def _first_blocking_context(frame: WorkspaceFrame) -> SafetyContext | None:
    for context in frame.safety_contexts:
        if context.directive in {
            SafetyResponseDirective.SAFE_REDIRECT,
            SafetyResponseDirective.REFUSE,
        }:
            return context
    return None


def _turn_intent(context: SafetyContext) -> str:
    if context.directive is SafetyResponseDirective.SAFE_REDIRECT:
        return "safe_redirect"
    return "safety_refusal"


def _response_text(context: SafetyContext) -> str:
    if context.directive is SafetyResponseDirective.SAFE_REDIRECT:
        return _safe_redirect_text(context)
    return _refusal_text(context)


def _safe_redirect_text(context: SafetyContext) -> str:
    if context.category is SafetyContextCategory.SELF_HARM:
        return (
            "I cannot help with instructions for self-harm. "
            "If you may be in immediate danger, contact local emergency services now. "
            "If you can, move away from anything you could use to hurt yourself and reach out "
            "to someone nearby or a crisis support line. I can stay with you and help you focus "
            "on the next safe minute."
        )
    return (
        "I cannot help with actionable dangerous instructions. "
        "I can help with safer alternatives, prevention, de-escalation, "
        "or getting appropriate support."
    )


def _refusal_text(context: SafetyContext) -> str:
    if context.category is SafetyContextCategory.PERSONAL_DATA:
        return (
            "I cannot help steal, expose, or misuse credentials or personal data. "
            "I can help with account recovery, defensive security, or safe incident response steps."
        )
    return (
        "I cannot help with instructions that enable physical harm or illegal dangerous activity. "
        "I can help with safety-focused information, prevention, or harmless alternatives."
    )
