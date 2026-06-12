"""MemoryRetrievalStep / MemoryWriteStep のスレッドオフロードテスト。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import time
from typing import TYPE_CHECKING, override

import pytest

from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import MemoryRetrievalResult, MemoryWriteResult, StepStatus
from iris.cognitive.memory.policy import MemoryWritePolicy
from iris.cognitive.memory.retrieval import MemoryRetrievalStep
from iris.cognitive.memory.write import MemoryWriteStep
from iris.cognitive.perception.basic import SimplePerceptionStep
from iris.contracts.memory import (
    MemoryId,
    MemoryQuery,
    MemoryRecord,
    MemorySearchResult,
)
from iris.contracts.observations import (
    ActorMessageObservation,
    ObservationContext,
    ObservationKind,
)
from iris.core.ids import ObservationId, SessionId

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.cognitive.memory.candidates import MemoryCandidate


class BlockingDetectorRetriever:
    """呼び出しがイベントループスレッドで走ったら検出するスタブレトリーバー。"""

    def __init__(self, results: Sequence[MemorySearchResult]) -> None:
        """検索結果で初期化する。

        Args:
            results: 返すべき検索結果。
        """
        self._results = tuple(results)
        self.call_count = 0

    def search(self, query: MemoryQuery) -> Sequence[MemorySearchResult]:
        # イベントループスレッドで呼ばれたかどうかを時間で簡易検出
        _ = query
        time.sleep(0.05)
        self.call_count += 1
        return self._results


class BlockingDetectorStore:
    """呼び出しがイベントループスレッドで走ったら検出するスタブストア。"""

    def __init__(self) -> None:
        """空の更新リストで初期化する。"""
        self.updated: list[MemoryRecord] = []

    def search(self, query: MemoryQuery) -> Sequence[MemorySearchResult]:
        _ = query
        time.sleep(0.05)
        return ()

    def get(self, memory_id: MemoryId) -> MemoryRecord | None:
        _ = memory_id
        return None

    def put(self, record: MemoryRecord) -> None:
        _ = record

    def update(self, record: MemoryRecord) -> MemoryRecord:
        time.sleep(0.05)
        self.updated.append(record)
        return record

    def archive(
        self,
        memory_id: MemoryId,
        *,
        archived: bool = True,
    ) -> MemoryRecord | None:
        _ = memory_id, archived
        return None

    def filter(self, query: MemoryQuery) -> Sequence[MemoryRecord]:
        _ = query
        return ()


class AlwaysAcceptPolicy(MemoryWritePolicy):
    """常に候補を受け入れるポリシー。"""

    @override
    def accept(self, candidate: MemoryCandidate) -> bool:
        _ = candidate
        return True


def actor_message(text: str = "hello") -> ActorMessageObservation:
    """テスト用 ActorMessageObservation を返す。

    Returns:
        ActorMessageObservation: テスト用観測。
    """
    return ActorMessageObservation(
        observation_id=ObservationId("obs-steps"),
        session_id=SessionId("session-steps"),
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        context=ObservationContext(),
        text=text,
    )


@pytest.mark.anyio
async def test_memory_retrieval_step_offloads_search() -> None:
    """MemoryRetrievalStep がイベントループをブロックせずに検索することを確認する。"""
    memory = MemorySearchResult(
        record=MemoryRecord(id=MemoryId("m-offload"), text="blocking test"),
        score=1.0,
    )
    retriever = BlockingDetectorRetriever((memory,))
    step = MemoryRetrievalStep(retriever, limit=5)

    frame = FrameBuilder().build_initial(actor_message())
    frame = FrameBuilder().apply(frame, await SimplePerceptionStep().run(frame))

    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        for _ in range(10):
            await asyncio.sleep(0.01)
            ticks += 1

    result: MemoryRetrievalResult
    result, _ticks = await asyncio.gather(
        step.run(frame),
        ticker(),
    )

    assert result.status == StepStatus.OK
    assert ticks > 0, "ticker should have progressed while search was offloaded"


@pytest.mark.anyio
async def test_memory_write_step_offloads_update() -> None:
    """MemoryWriteStep がイベントループをブロックせずに書き込むことを確認する。"""
    store = BlockingDetectorStore()
    step = MemoryWriteStep(
        store=store,
        policy=AlwaysAcceptPolicy(),
    )

    frame = FrameBuilder().build_initial(actor_message("I like tea"))
    frame = FrameBuilder().apply(frame, await SimplePerceptionStep().run(frame))

    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        for _ in range(10):
            await asyncio.sleep(0.01)
            ticks += 1

    result: MemoryWriteResult
    result, _ticks = await asyncio.gather(
        step.run(frame),
        ticker(),
    )

    assert result.status == StepStatus.OK
    assert ticks > 0, "ticker should have progressed while update was offloaded"
    assert len(store.updated) >= 1
