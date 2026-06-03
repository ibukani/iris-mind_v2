from iris.cognitive.cycle.models import ActionSelectionResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.cognitive.workspace.frame import WorkspaceFrame
from iris.contracts.actions import ActionPlan


class SimpleActionSelectionStep(PipelineStep[ActionSelectionResult]):
    name = "action_selection"

    async def run(self, frame: WorkspaceFrame) -> ActionSelectionResult:
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
