"""MemoryWriteStep vector index sync tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.adapters.memory.vector_index import InMemoryVectorMemoryIndex
from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import PerceptionResult, StepStatus
from iris.cognitive.memory.write import MemoryWriteStep
from iris.contracts.memory import MemoryId
from iris.contracts.observations import (
    ActorMessageObservation,
    ObservationContext,
    ObservationKind,
)
from iris.core.ids import ObservationId, SessionId

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import WorkspaceFrame


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
    vector_index = InMemoryVectorMemoryIndex(_embed_text)
    step = MemoryWriteStep(store=store, vector_index=vector_index)

    frame = _build_frame("覚えて: jasmine tea is my favorite")
    result = await step.run(frame)

    assert result.status == StepStatus.OK
    assert len(result.written_ids) == 1

    vector_results = vector_index.search("tea", limit=5)
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


def _embed_text(text: str) -> tuple[float, float]:
    """Tea / coffee キーワードに基づく 2 次元埋め込み。

    Returns:
        tuple[float, float]: 埋め込みベクトル。
    """
    return (
        1.0 if "tea" in text.casefold() else 0.0,
        1.0 if "coffee" in text.casefold() else 0.0,
    )
