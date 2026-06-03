from typing import Protocol, TypeVar

from iris.cognitive.cycle.models import PipelineStepResult
from iris.cognitive.workspace.frame import WorkspaceFrame

ResultT = TypeVar("ResultT", bound=PipelineStepResult, covariant=True)


class PipelineStep(Protocol[ResultT]):
    name: str

    async def run(self, frame: WorkspaceFrame) -> ResultT: ...
