"""Cognitive Runtime v0.1の最小限のアプリケーション構成ルート.

すべての層を配線するためのエントリポイント.
認知ポリシーロジック、サービロケータ、グローバルレジストリは使用しない。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.service import CognitiveCycle
from iris.contracts.actions import ActionPlan, PresentedOutput
from iris.presentation.presenter import Presenter, SimplePresenter
from iris.safety.action_gate import ActionSafetyGate, AllowAllActionGate, GateDecision
from iris.safety.output_filter import AllowAllOutputGate, OutputSafetyGate

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.cognitive.cycle.models import CycleResult, PipelineStepResult
    from iris.cognitive.cycle.pipeline import PipelineStep
    from iris.cognitive.workspace.frame import SituationContextSnapshot
    from iris.contracts.observations import Observation


class IrisApp:
    """Iris認知ランタイムの最小限のアプリケーション構成ルート."""

    def __init__(
        self,
        steps: Sequence[PipelineStep[PipelineStepResult]] | None = None,
        fallback_plan: ActionPlan | None = None,
        presenter: Presenter | None = None,
        action_safety_gate: ActionSafetyGate | None = None,
        output_safety_gate: OutputSafetyGate | None = None,
        cycle: CognitiveCycle | None = None,
    ) -> None:
        """オプションの依存関係オーバーライドでアプリケーションを初期化する.

        Args:
            steps: Pipeline steps used when no cycle is provided.
            fallback_plan: Default plan returned on cycle failure.
            presenter: Output presenter override.
            action_safety_gate: Action gate override.
            output_safety_gate: Output gate override.
            cycle: Pre-wired cognitive cycle; if provided, steps is ignored.

        Raises:
            ValueError: If neither steps nor cycle is provided.
        """
        if fallback_plan is None:
            fallback_plan = ActionPlan(
                turn_intent="no_action",
                candidate_text=None,
                should_respond=False,
                priority=-1,
            )
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
        self._presenter = presenter or SimplePresenter()
        self._action_safety_gate = action_safety_gate or AllowAllActionGate()
        self._output_safety_gate = output_safety_gate or AllowAllOutputGate()

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
        safety_decision = await self._action_safety_gate.check_plan(plan)
        if safety_decision.decision is GateDecision.BLOCK:
            return PresentedOutput(text=None)
        output: PresentedOutput = await self._presenter.present(plan)
        output_decision = await self._output_safety_gate.check_output(output)
        if output_decision.decision is GateDecision.BLOCK:
            return PresentedOutput(text=None)
        return output
