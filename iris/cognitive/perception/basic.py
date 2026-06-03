from iris.cognitive.cycle.models import PerceptionResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.cognitive.workspace.frame import WorkspaceFrame


class SimplePerceptionStep(PipelineStep[PerceptionResult]):
    name = "perception"

    async def run(self, frame: WorkspaceFrame) -> PerceptionResult:
        obs = frame.observation
        return PerceptionResult(
            step_name=self.name,
            status=StepStatus.OK,
            text=getattr(obs, "text", str(obs.kind)),
            language=None,
            intent_hint=None,
        )
