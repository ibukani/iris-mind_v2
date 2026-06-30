"""長期記憶の誤保存を防ぐ regression tests。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import PerceptionResult, StepStatus
from iris.cognitive.memory.write import MemoryWriteStep
from iris.contracts.observations import ActorMessageObservation, ObservationContext, ObservationKind
from iris.core.ids import ObservationId, SessionId

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import WorkspaceFrame


def _build_frame(text: str) -> WorkspaceFrame:
    """指定テキストを持つ WorkspaceFrame を構築する。

    Returns:
        WorkspaceFrame: 構築されたフレーム。
    """
    observation = ActorMessageObservation(
        observation_id=ObservationId("obs-negative"),
        session_id=SessionId("session-negative"),
        context=ObservationContext(),
        occurred_at=datetime(2026, 6, 30, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
    )
    frame = FrameBuilder().build_initial(observation)
    return FrameBuilder().apply(
        frame,
        PerceptionResult(step_name="perception", status=StepStatus.OK, text=text),
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "text",
    [
        "この変数をxと呼んで",
        "彼を" + "太郎と呼んで",
        "このプロジェクトをIrisと呼んで",
    ],
)
async def test_memory_write_step_does_not_store_object_labels_as_preferred_name(
    text: str,
) -> None:
    """対象物への命名指示をユーザー希望呼称として保存しない。"""
    store = InMemoryMemoryStore()
    result = await MemoryWriteStep(store=store).run(_build_frame(text))

    assert result.status == StepStatus.SKIPPED
    assert result.written_ids == ()
    assert result.rejected_count >= 0


@pytest.mark.anyio
@pytest.mark.parametrize(
    "text",
    [
        "私は" + "キリスト" + "教徒です",
        "I am " + "Christian",
    ],
)
async def test_memory_write_step_does_not_store_sensitive_self_identification(
    text: str,
) -> None:
    """センシティブな自己紹介を hot path で長期記憶へ保存しない。"""
    store = InMemoryMemoryStore()
    result = await MemoryWriteStep(store=store).run(_build_frame(text))

    assert result.status == StepStatus.SKIPPED
    assert result.written_ids == ()
    assert result.rejected_count >= 1


@pytest.mark.anyio
async def test_memory_write_step_ignores_ambiguous_preference_statement() -> None:
    """曖昧な好み表現は長期 preference memory として保存しない。"""
    store = InMemoryMemoryStore()
    result = await MemoryWriteStep(store=store).run(_build_frame("私は青が好きかもしれない"))

    assert result.status == StepStatus.SKIPPED
    assert result.written_ids == ()
