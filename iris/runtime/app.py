"""Cognitive Runtime v0.1の最小限のアプリケーション構成ルート.

すべての層を配線するためのエントリポイント.
認知ポリシーロジック、サービロケータ、グローバルレジストリは使用しない。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.service import CognitiveCycle
from iris.contracts.actions import (
    ActionPlan,
    PresentedOutput,
    presented_output_with_policy_metadata,
)
from iris.runtime.wiring.presentation import wire_output_pipeline

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.cognitive.cycle.models import CycleResult, PipelineStepResult
    from iris.cognitive.cycle.pipeline import PipelineStep
    from iris.contracts.observations import Observation
    from iris.contracts.workspace_context import SituationContextSnapshot
    from iris.runtime.output_pipeline import RuntimeOutputPipeline


class IrisApp:
    """Iris認知ランタイムの最小限のアプリケーション構成ルート."""

    def __init__(
        self,
        steps: Sequence[PipelineStep[PipelineStepResult]] | None = None,
        fallback_plan: ActionPlan | None = None,
        output_pipeline: RuntimeOutputPipeline | None = None,
        cycle: CognitiveCycle | None = None,
    ) -> None:
        """オプションの依存関係オーバーライドでアプリケーションを初期化する.

        Args:
            steps: Pipeline steps used when no cycle is provided.
            fallback_plan: Default plan returned on cycle failure.
            output_pipeline: Pipeline for action presentation and safety.
            cycle: Pre-wired cognitive cycle; if provided, steps is ignored.

        Raises:
            ValueError: If neither steps nor cycle is provided.
        """
        if fallback_plan is None:
            fallback_plan = ActionPlan.no_action()
        if cycle is not None:
            self._cycle = cycle
        else:
            if steps is None:
                err = "steps or cycle must be provided"
                raise ValueError(err)
            self._cycle = CognitiveCycle(
                steps=steps,
                frame_builder=FrameBuilder(),
                fallback_plan=fallback_plan,
            )
        self._output_pipeline = output_pipeline or wire_output_pipeline()

    async def process_observation(
        self,
        observation: Observation,
        *,
        situation_context: SituationContextSnapshot | None = None,
    ) -> PresentedOutput:
        """完全な認知パイプラインを通して単一の観測を処理する.

        Args:
            observation: The incoming observation to process.
            situation_context: Optional runtime-assembled situation context.

        Returns:
            Presented output, or an empty output if the action was blocked.
        """
        cycle_result: CycleResult = await self._cycle.run(
            observation,
            situation_context=situation_context,
        )
        plan: ActionPlan = cycle_result.selected_plan
        if plan.is_no_action:
            return PresentedOutput(text=None)

        output = await self._output_pipeline.present_action_plan(plan)
        constraint_names = tuple(item.name for item in cycle_result.frame.constraints)
        safety_contexts = tuple(
            context
            for constraint in cycle_result.frame.constraints
            if constraint.safety_context is not None
            for context in (constraint.safety_context,)
        )
        return presented_output_with_policy_metadata(
            output,
            constraint_names=constraint_names,
            safety_contexts=safety_contexts,
        )
