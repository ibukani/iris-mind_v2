"""認知パイプラインのPipelineStepプロトコル定義。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeVar

from iris.cognitive.cycle.models import PipelineStepResult

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import WorkspaceFrame

ResultT_co = TypeVar("ResultT_co", bound=PipelineStepResult, covariant=True)


class PipelineStep(Protocol[ResultT_co]):
    """認知パイプラインの単一ステップのプロトコル。"""

    name: str

    async def run(self, frame: WorkspaceFrame) -> ResultT_co:
        """現在のワークスペースフレームに対してステップを実行し、型付き結果を返す。"""
        ...
