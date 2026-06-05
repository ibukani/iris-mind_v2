"""メモリ検索パイプラインステップとフレームエンリッチメントのテスト。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import StepStatus
from iris.cognitive.memory.retrieval import MemoryRetrievalStep
from iris.cognitive.perception.basic import SimplePerceptionStep
from iris.cognitive.workspace.frame import WorkspaceFrame
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.memory import MemoryId, MemoryQuery, MemoryRecord, MemorySearchResult
from iris.contracts.observations import ActorMessageObservation, ObservationContext, ObservationKind
from iris.core.ids import ActorId, ExternalRef, ObservationId, SessionId, SpaceId
from tests.helpers.immutability import assert_frozen_field

if TYPE_CHECKING:
    from collections.abc import Sequence


class StubMemoryRetriever:
    """クエリを記録して固定結果を返すスタブメモリ検索器。"""

    def __init__(self, results: Sequence[MemorySearchResult]) -> None:
        """固定検索結果で初期化する。"""
        self.queries: list[MemoryQuery] = []
        self._results = tuple(results)

    def search(self, query: MemoryQuery) -> Sequence[MemorySearchResult]:
        """クエリを記録して固定結果を返す。

        Returns:
            Sequence[MemorySearchResult]: 事前定義された固定結果。
        """
        self.queries.append(query)
        return self._results


def actor_message(
    text: str = "hello tea",
    context: ObservationContext | None = None,
) -> ActorMessageObservation:
    """指定されたテキストを持つActorMessageObservationを返す。

    Returns:
        ActorMessageObservation: 構築済みの観測。
    """
    return ActorMessageObservation(
        observation_id=ObservationId("obs-memory"),
        session_id=SessionId("session-memory"),
        context=context or ObservationContext(),
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
    )


@pytest.mark.anyio
async def test_memory_retrieval_step_returns_typed_results() -> None:
    """MemoryRetrievalStepがメモリを検索してフレームをエンリッチすることを確認する。"""
    memory = MemorySearchResult(
        record=MemoryRecord(id=MemoryId("m1"), text="User likes tea."),
        score=1.0,
    )
    retriever = StubMemoryRetriever((memory,))
    builder = FrameBuilder()
    frame = WorkspaceFrame(observation=actor_message())
    frame = builder.apply(frame, await SimplePerceptionStep().run(frame))

    result = await MemoryRetrievalStep(retriever, limit=2).run(frame)
    builder.apply(frame, result)

    assert result.status == StepStatus.OK
    assert result.memories == (memory,)
    assert retriever.queries == [MemoryQuery(text="hello tea", limit=2)]


@pytest.mark.asyncio
async def test_memory_retrieval_query_uses_actor_and_space_scope() -> None:
    """MemoryRetrievalStepがframe contextのActorId/SpaceIdをMemoryQueryへ渡すことを確認する。"""
    actor = Identity(
        actor_id=ActorId("actor-memory"),
        actor_kind=ActorKind.HUMAN,
        display_name="Mina",
        provider="test",
        provider_subject=ExternalRef("mina"),
    )
    retriever = StubMemoryRetriever(())
    frame = FrameBuilder().build_initial(
        actor_message(
            context=ObservationContext(
                actor=actor,
                space_id=SpaceId("space-memory"),
            )
        )
    )
    frame = FrameBuilder().apply(frame, await SimplePerceptionStep().run(frame))

    result = await MemoryRetrievalStep(retriever, limit=3).run(frame)

    assert result.status == StepStatus.OK
    assert retriever.queries == [
        MemoryQuery(
            text="hello tea",
            actor_id=ActorId("actor-memory"),
            space_id=SpaceId("space-memory"),
            limit=3,
        )
    ]
    assert frame.memory_summary.retrieved_memories == ()


@pytest.mark.anyio
async def test_memory_retrieval_step_skips_without_interpreted_text() -> None:
    """フレームに解釈テキストがない場合にMemoryRetrievalStepがスキップすることを確認する。"""
    retriever = StubMemoryRetriever(())
    frame = WorkspaceFrame(observation=actor_message())

    result = await MemoryRetrievalStep(retriever).run(frame)

    assert result.status == StepStatus.SKIPPED
    assert result.memories == ()
    assert retriever.queries == []


def test_workspace_frame_memory_is_not_directly_mutated() -> None:
    """WorkspaceFrame.memory_summaryがその場で変更できないことを確認する。"""
    frame = WorkspaceFrame(observation=actor_message())

    assert_frozen_field(frame, "memory_summary", frame.memory_summary)
