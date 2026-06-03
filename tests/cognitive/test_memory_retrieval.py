from __future__ import annotations

from collections.abc import Sequence
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import StepStatus
from iris.cognitive.memory.retrieval import MemoryRetrievalStep
from iris.cognitive.perception.basic import SimplePerceptionStep
from iris.cognitive.workspace.frame import WorkspaceFrame
from iris.contracts.memory import MemoryId, MemoryQuery, MemoryRecord, MemorySearchResult
from iris.contracts.observations import ObservationKind, UserMessageObservation
from iris.core.ids import ObservationId, SessionId


class StubMemoryRetriever:
    def __init__(self, results: Sequence[MemorySearchResult]) -> None:
        self.queries: list[MemoryQuery] = []
        self._results = tuple(results)

    def search(self, query: MemoryQuery) -> Sequence[MemorySearchResult]:
        self.queries.append(query)
        return self._results


def user_message(text: str = "hello tea") -> UserMessageObservation:
    return UserMessageObservation(
        observation_id=ObservationId("obs-memory"),
        session_id=SessionId("session-memory"),
        actor=None,
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.USER_MESSAGE,
        text=text,
    )


@pytest.mark.anyio
async def test_memory_retrieval_step_returns_typed_results() -> None:
    memory = MemorySearchResult(
        record=MemoryRecord(id=MemoryId("m1"), text="User likes tea."),
        score=1.0,
    )
    retriever = StubMemoryRetriever((memory,))
    builder = FrameBuilder()
    frame = WorkspaceFrame(observation=user_message())
    frame = builder.apply(frame, await SimplePerceptionStep().run(frame))

    result = await MemoryRetrievalStep(retriever, limit=2).run(frame)
    enriched = builder.apply(frame, result)

    assert result.status == StepStatus.OK
    assert result.memories == (memory,)
    assert retriever.queries == [MemoryQuery(text="hello tea", limit=2)]
    assert frame.memory_summary.retrieved_memories == ()
    assert enriched.memory_summary.retrieved_memories == (memory,)


@pytest.mark.anyio
async def test_memory_retrieval_step_skips_without_interpreted_text() -> None:
    retriever = StubMemoryRetriever(())
    frame = WorkspaceFrame(observation=user_message())

    result = await MemoryRetrievalStep(retriever).run(frame)

    assert result.status == StepStatus.SKIPPED
    assert result.memories == ()
    assert retriever.queries == []


def test_workspace_frame_memory_is_not_directly_mutated() -> None:
    frame = WorkspaceFrame(observation=user_message())

    with pytest.raises(FrozenInstanceError):
        frame.memory_summary = frame.memory_summary  # type: ignore[misc]
