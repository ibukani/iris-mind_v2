from collections.abc import Sequence

from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import CycleResult, PipelineStepResult
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.cognitive.workspace.frame import WorkspaceFrame
from iris.contracts.actions import ActionPlan
from iris.contracts.observations import Observation


class CognitiveCycle:
    def __init__(
        self,
        steps: Sequence[PipelineStep[PipelineStepResult]],
        frame_builder: FrameBuilder,
        fallback_plan: ActionPlan,
    ) -> None:
        self._steps = tuple(steps)
        self._frame_builder = frame_builder
        self._fallback_plan = fallback_plan

    async def run(self, observation: Observation) -> CycleResult:
        frame = WorkspaceFrame(observation=observation)

        for step in self._steps:
            result = await step.run(frame)
            frame = self._frame_builder.apply(frame, result)

        selected = self._select_action_plan(frame)
        return CycleResult(frame=frame, selected_plan=selected)

    def _select_action_plan(self, frame: WorkspaceFrame) -> ActionPlan:
        if frame.candidate_action_plans:
            return max(frame.candidate_action_plans, key=lambda plan: plan.priority)
        return self._fallback_plan
