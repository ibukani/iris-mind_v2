"""基本アクション選択パイプラインステップ。"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from iris.cognitive.cycle.models import ActionSelectionResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.contracts.actions import ActionPlan
from iris.features.basic_action.presenter import SimplePresenter
from iris.features.definition import FeatureDefinition

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


def define_basic_action_feature() -> FeatureDefinition:
    """基本アクション機能の定義を組み立てる。

    Returns:
        Basic action feature vertical sliceの定義。
    """
    return FeatureDefinition(
        name="basic_action",
        cognitive_steps=(SimpleActionSelectionStep(),),
        action_plan_presenters=(SimplePresenter(),),
    )
