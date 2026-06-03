"""Minimal application composition root for Cognitive Runtime v0.1.

This is the entry point for wiring all layers together.
No cognitive policy logic, no service locator, no global registry.
"""

from collections.abc import Sequence

from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import CycleResult, PipelineStepResult
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.cognitive.cycle.service import CognitiveCycle
from iris.contracts.actions import ActionPlan, PresentedOutput
from iris.contracts.observations import Observation
from iris.presentation.presenter import Presenter, SimplePresenter
from iris.safety.action_gate import ActionSafetyGate, AllowAllActionGate, GateDecision
from iris.safety.output_filter import AllowAllOutputGate, OutputSafetyGate


class IrisApp:
    def __init__(
        self,
        steps: Sequence[PipelineStep[PipelineStepResult]] | None = None,
        fallback_plan: ActionPlan | None = None,
        presenter: Presenter | None = None,
        action_safety_gate: ActionSafetyGate | None = None,
        output_safety_gate: OutputSafetyGate | None = None,
        cycle: CognitiveCycle | None = None,
    ) -> None:
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
                raise ValueError("steps or cycle must be provided")
            self._cycle = CognitiveCycle(
                steps=steps,
                frame_builder=FrameBuilder(),
                fallback_plan=fallback_plan,
            )
        self._presenter = presenter or SimplePresenter()
        self._action_safety_gate = action_safety_gate or AllowAllActionGate()
        self._output_safety_gate = output_safety_gate or AllowAllOutputGate()

    async def process_observation(self, observation: Observation) -> PresentedOutput:
        cycle_result: CycleResult = await self._cycle.run(observation)
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
