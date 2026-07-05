"""開発・診断用 echo action feature。"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from iris.cognitive.cycle.models import ActionSelectionResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.contracts.actions import ActionPlan
from iris.features.definition import FeatureDefinition, FeatureKind

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import WorkspaceFrame


class DiagnosticEchoActionSelectionStep(PipelineStep[ActionSelectionResult]):
    """入力テキストをそのまま返す開発・診断用 action selection step。"""

    name = "diagnostic_echo_action_selection"

    @override
    async def run(self, frame: WorkspaceFrame) -> ActionSelectionResult:
        """フレームの解釈入力テキストから診断用 echo ActionPlan を作る。

        Returns:
            診断用 ActionPlan を含む結果。入力テキストが無い場合は no-send 候補。
        """
        text = frame.interpreted_input.text if frame.interpreted_input else None
        plan = ActionPlan(
            turn_intent="respond",
            candidate_text=text,
            should_respond=text is not None,
            priority=0,
        )
        return ActionSelectionResult(
            step_name=self.name,
            status=StepStatus.OK,
            action_plans=(plan,),
        )


def define_basic_action_feature() -> FeatureDefinition:
    """Diagnostic echo action feature の定義を組み立てる。

    Returns:
        development/debug runtime 専用の diagnostic feature 定義。
    """
    return FeatureDefinition(
        name="basic_action",
        kind=FeatureKind.DIAGNOSTIC,
        cognitive_steps=(DiagnosticEchoActionSelectionStep(),),
    )
