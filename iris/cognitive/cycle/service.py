"""CognitiveCycle：ステップを実行しアクションプランを選択するパイプラインコーディネータ。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.cognitive.cycle.models import CycleResult, PipelineStepResult

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.cognitive.cycle.frame_builder import FrameBuilder
    from iris.cognitive.cycle.pipeline import PipelineStep
    from iris.cognitive.workspace.frame import SituationContextSnapshot, WorkspaceFrame
    from iris.contracts.actions import ActionPlan
    from iris.contracts.observations import Observation


class CognitiveCycle:
    """認知パイプラインを指揮する：ステップ実行、結果適用、プラン選択。"""

    def __init__(
        self,
        steps: Sequence[PipelineStep[PipelineStepResult]],
        frame_builder: FrameBuilder,
        fallback_plan: ActionPlan,
    ) -> None:
        """パイプラインステップ、フレームビルダー、フォールバックプランで初期化する。

        Args:
            steps: 実行するパイプラインステップの順序付きシーケンス。
            frame_builder: ステップ結果をフレームに適用するビルダー。
            fallback_plan: 候補プランが選択されなかった場合に使用する ActionPlan。
        """
        self._steps = tuple(steps)
        self._frame_builder = frame_builder
        self._fallback_plan = fallback_plan

    async def run(
        self,
        observation: Observation,
        *,
        situation_context: SituationContextSnapshot | None = None,
    ) -> CycleResult:
        """与えられた観測に対して認知パイプラインを実行し、結果を返す。

        Args:
            observation: 処理対象の観測。
            situation_context: ランタイムから組み立てられた任意の状況コンテキスト。

        Returns:
            CycleResult: パイプライン実行結果(最終フレームと選択されたアクションプラン)。
        """
        frame = self._frame_builder.build_initial(
            observation,
            situation_context=situation_context,
        )

        for step in self._steps:
            result = await step.run(frame)
            frame = self._frame_builder.apply(frame, result)

        selected = self._select_action_plan(frame)
        return CycleResult(frame=frame, selected_plan=selected)

    def _select_action_plan(self, frame: WorkspaceFrame) -> ActionPlan:
        plans = frame.candidate_action_plans
        if not plans:
            return self._fallback_plan
        selected: ActionPlan = plans[0]
        best_priority = selected.priority
        for plan in plans[1:]:
            if plan.priority > best_priority:
                selected = plan
                best_priority = plan.priority
        return selected
