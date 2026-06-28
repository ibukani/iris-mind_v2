"""基本アクション選択パイプラインステップ。"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from iris.cognitive.cycle.models import ActionSelectionResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.contracts.actions import ActionPlan

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import WorkspaceFrame


class SimpleActionSelectionStep(PipelineStep[ActionSelectionResult]):
    """解釈入力から基本応答アクションプランを作成するパイプラインステップ。"""

    name = "action_selection"

    @override
    async def run(self, frame: WorkspaceFrame) -> ActionSelectionResult:
        """フレームの解釈入力テキストから応答アクションプランを構築する。

        Returns:
            ActionSelectionResult: 生成されたアクションプランを含む結果。
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
