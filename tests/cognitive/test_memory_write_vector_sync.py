"""MemoryWriteStep vector index sync tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, override

import pytest

from iris.adapters.embeddings.fake import DeterministicFakeEmbedding
from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.adapters.memory.vector_index import InMemoryVectorMemoryIndex
from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import PerceptionResult, StepStatus
from iris.cognitive.memory.write import MemoryWriteStep
from iris.contracts.memory import MemoryId, VectorMemoryEntry, VectorMemoryIndexError
from iris.contracts.observations import (
    ActorMessageObservation,
    ObservationContext,
    ObservationKind,
)
from iris.core.ids import ObservationId, SessionId

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import WorkspaceFrame


class _FailingVectorIndex(InMemoryVectorMemoryIndex):
    @override
    def upsert(self, entry: VectorMemoryEntry) -> None:
        """Index failure を再現する。

        Raises:
            VectorMemoryIndexError: 常に発生する。
        """
        del entry
        message = "unavailable"
        raise VectorMemoryIndexError(message)


def _actor_message(text: str) -> ActorMessageObservation:
    """ActorMessageObservation を返す。

    Returns:
        ActorMessageObservation: 構築された観測。
    """
    return ActorMessageObservation(
        observation_id=ObservationId("obs-v1"),
        session_id=SessionId("session-v1"),
        context=ObservationContext(),
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
    )


def _build_frame(text: str) -> WorkspaceFrame:
    """解釈済みテキストを持つフレームを構築する。

    Returns:
        WorkspaceFrame: 構築されたフレーム。
    """
    observation = _actor_message(text)
    frame = FrameBuilder().build_initial(observation)
    return FrameBuilder().apply(
        frame,
        PerceptionResult(step_name="perception", status=StepStatus.OK, text=text),
    )


@pytest.mark.anyio
async def test_memory_write_step_upserts_to_vector_index() -> None:
    """MemoryWriteStep が vector_index にも upsert することを確認する。"""
    store = InMemoryMemoryStore()
    vector_index = InMemoryVectorMemoryIndex()
    embedding = DeterministicFakeEmbedding(dimension=2)
    step = MemoryWriteStep(store=store, vector_index=vector_index, embedding=embedding)

    frame = _build_frame("覚えて: jasmine tea is my favorite")
    result = await step.run(frame)

    assert result.status == StepStatus.OK
    assert len(result.written_ids) == 1

    vector_results = vector_index.search(embedding.embed("tea"), limit=5)
    assert len(vector_results) == 1
    assert vector_results[0].memory_id == MemoryId(result.written_ids[0])


@pytest.mark.anyio
async def test_memory_write_step_skips_vector_index_when_none() -> None:
    """vector_index=None の場合、通常の write のみ動作する。"""
    store = InMemoryMemoryStore()
    step = MemoryWriteStep(store=store)

    frame = _build_frame("覚えて: jasmine tea is my favorite")
    result = await step.run(frame)

    assert result.status == StepStatus.OK
    assert len(result.written_ids) == 1


@pytest.mark.anyio
async def test_memory_write_step_keeps_canonical_record_when_vector_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Vector failure は既に成功した canonical write を破棄しない。"""
    store = InMemoryMemoryStore()
    step = MemoryWriteStep(
        store=store,
        vector_index=_FailingVectorIndex(),
        embedding=DeterministicFakeEmbedding(dimension=2),
    )

    result = await step.run(_build_frame("覚えて: jasmine tea is my favorite"))

    assert result.status == StepStatus.OK
    assert store.get(MemoryId(result.written_ids[0])) is not None
    assert "memory vector index upsert failed" in caplog.text
    assert "jasmine tea is my favorite" not in caplog.text


class _MismatchedDimensionEmbedding:
    @property
    def model_id(self) -> str:
        """Model identifier for compatibility metadata."""
        return "mismatch"

    @property
    def dimension(self) -> int:
        """Declared dimension intentionally differs from embed output."""
        return 3

    def embed(self, text: str) -> tuple[float, ...]:
        """Declared dimension と異なる vector を返す。

        Returns:
            Declared dimension と異なる 2 次元 vector。
        """
        del text
        return (1.0, 0.0)

    def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        """Declared dimension と異なる batch vector を返す。

        Returns:
            入力数と同じ件数の mismatch vector。
        """
        return tuple(self.embed(text) for text in texts)


@pytest.mark.anyio
async def test_memory_write_step_keeps_canonical_record_on_vector_dimension_mismatch(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """InMemory index の dimension mismatch でも fail-open で正本 write を保持する。"""
    store = InMemoryMemoryStore()
    step = MemoryWriteStep(
        store=store,
        vector_index=InMemoryVectorMemoryIndex(),
        embedding=_MismatchedDimensionEmbedding(),
    )

    result = await step.run(_build_frame("覚えて: jasmine tea is my favorite"))

    assert result.status == StepStatus.OK
    assert store.get(MemoryId(result.written_ids[0])) is not None
    assert "memory vector index upsert failed" in caplog.text
