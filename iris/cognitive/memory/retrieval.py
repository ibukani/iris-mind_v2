from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from iris.cognitive.cycle.models import MemoryRetrievalResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.cognitive.workspace.frame import WorkspaceFrame
from iris.contracts.memory import MemoryQuery, MemorySearchResult


class MemoryRetriever(Protocol):
    def search(self, query: MemoryQuery) -> Sequence[MemorySearchResult]: ...


class MemoryRetrievalStep(PipelineStep[MemoryRetrievalResult]):
    name = "memory_retrieval"

    def __init__(self, retriever: MemoryRetriever, *, limit: int = 5) -> None:
        self._retriever = retriever
        self._limit = limit

    async def run(self, frame: WorkspaceFrame) -> MemoryRetrievalResult:
        if frame.interpreted_input is None or frame.interpreted_input.text is None:
            return MemoryRetrievalResult(
                step_name=self.name,
                status=StepStatus.SKIPPED,
                reason="no interpreted input text",
                memories=(),
            )

        query = MemoryQuery(
            text=frame.interpreted_input.text,
            subject_id=frame.observation.actor.user_id if frame.observation.actor else None,
            limit=self._limit,
        )
        memories = tuple(self._retriever.search(query))
        return MemoryRetrievalResult(
            step_name=self.name,
            status=StepStatus.OK,
            memories=memories,
        )
