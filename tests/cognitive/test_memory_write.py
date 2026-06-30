"""MemoryWritePolicy と MemoryWriteStep のテスト。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import PerceptionResult, StepStatus
from iris.cognitive.memory.candidates import (
    MemoryCandidate,
    MemoryCandidateSource,
    MemoryRetentionPolicy,
)
from iris.cognitive.memory.policy import MemoryWritePolicy
from iris.cognitive.memory.write import MemoryWriteStep
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.memory import MemoryId, MemoryKind, MemoryQuery
from iris.contracts.observations import ActorMessageObservation, ObservationContext, ObservationKind
from iris.core.ids import ActorId, ExternalRef, ObservationId, SessionId, SpaceId

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import WorkspaceFrame


def _build_frame(
    text: str, *, actor_id: str | None = None, space_id: str | None = None
) -> WorkspaceFrame:
    """指定テキストと任意のアクター/スペースを持つフレームを構築する。

    Returns:
        WorkspaceFrame: 構築されたフレーム。
    """
    context = ObservationContext()
    if actor_id:
        context = ObservationContext(
            actor=Identity(
                actor_id=ActorId(actor_id),
                actor_kind=ActorKind.HUMAN,
                display_name="Test",
                provider="test",
                provider_subject=ExternalRef("test"),
            ),
            space_id=SpaceId(space_id) if space_id else None,
        )
    elif space_id:
        context = ObservationContext(space_id=SpaceId(space_id))

    observation = ActorMessageObservation(
        observation_id=ObservationId("obs-1"),
        session_id=SessionId("session-1"),
        context=context,
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
    )
    frame = FrameBuilder().build_initial(observation)
    return FrameBuilder().apply(
        frame,
        PerceptionResult(step_name="perception", status=StepStatus.OK, text=text),
    )


def test_memory_write_policy_rejects_empty_candidate() -> None:
    """空 text の候補は拒否されることを確認する。"""
    policy = MemoryWritePolicy()
    candidate = MemoryCandidate(text="   ", kind=MemoryKind.NOTE, salience=0.8, confidence=0.9)
    assert policy.accept(candidate) is False


def test_memory_write_policy_rejects_secret_like_candidate() -> None:
    """秘密情報を含む候補は拒否されることを確認する。"""
    policy = MemoryWritePolicy()
    secrets = [
        "my password is 12345",
        "APIキーはsk-abc123",
        "github_pat_xxx",
        "bearer token xyz",
    ]
    for text in secrets:
        candidate = MemoryCandidate(text=text, kind=MemoryKind.NOTE, salience=0.8, confidence=0.9)
        assert policy.accept(candidate) is False, f"should reject: {text}"


def test_memory_write_policy_accepts_normal_candidate() -> None:
    """通常の候補は許可されることを確認する。"""
    policy = MemoryWritePolicy()
    candidate = MemoryCandidate(
        text="User likes jasmine tea.",
        kind=MemoryKind.PREFERENCE,
        salience=0.7,
        confidence=0.85,
    )
    assert policy.accept(candidate) is True


def test_memory_write_policy_rejects_low_salience() -> None:
    """min_salience を下回る候補は拒否されることを確認する。"""
    policy = MemoryWritePolicy(min_salience=0.5)
    candidate = MemoryCandidate(text="normal", kind=MemoryKind.NOTE, salience=0.3, confidence=0.9)
    assert policy.accept(candidate) is False


def test_memory_write_policy_rejects_low_confidence() -> None:
    """min_confidence を下回る候補は拒否されることを確認する。"""
    policy = MemoryWritePolicy(min_confidence=0.5)
    candidate = MemoryCandidate(text="normal", kind=MemoryKind.NOTE, salience=0.8, confidence=0.3)
    assert policy.accept(candidate) is False


@pytest.mark.parametrize(
    ("source", "retention_policy", "review_required"),
    [
        (MemoryCandidateSource.IMPLICIT_CONVERSATION, MemoryRetentionPolicy.DURABLE, False),
        (MemoryCandidateSource.EXPLICIT_USER_REQUEST, MemoryRetentionPolicy.DURABLE, True),
        (MemoryCandidateSource.EXPLICIT_USER_REQUEST, MemoryRetentionPolicy.DISCARD, False),
    ],
)
def test_memory_write_policy_rejects_non_hot_path_candidates(
    source: MemoryCandidateSource,
    retention_policy: MemoryRetentionPolicy,
    *,
    review_required: bool,
) -> None:
    """暗黙・要審査・破棄候補を hot path から除外する。"""
    policy = MemoryWritePolicy()
    candidate = MemoryCandidate(
        text="候補",
        kind=MemoryKind.NOTE,
        salience=0.8,
        confidence=0.9,
        source=source,
        retention_policy=retention_policy,
        review_required=review_required,
    )
    assert policy.accept(candidate) is False


@pytest.mark.anyio
async def test_memory_write_step_writes_candidates_to_store() -> None:
    """MemoryWriteStep が候補をストアに書き込むことを確認する。"""
    store = InMemoryMemoryStore()
    step = MemoryWriteStep(store=store)
    frame = _build_frame("覚えて: ジャスミン茶が好き")

    result = await step.run(frame)

    assert result.status == StepStatus.OK
    assert len(result.written_ids) >= 1
    for memory_id in result.written_ids:
        record = store.get(MemoryId(memory_id))
        assert record is not None
        assert "ジャスミン茶" in record.text
        assert record.metadata["candidate_source"] in {
            MemoryCandidateSource.EXPLICIT_USER_REQUEST.value,
            MemoryCandidateSource.EXPLICIT_PREFERENCE.value,
        }
        assert record.metadata["retention_policy"] == MemoryRetentionPolicy.DURABLE.value
        assert record.metadata["review_required"] == "false"
        assert record.metadata["reason"]


@pytest.mark.anyio
async def test_memory_write_step_preserves_existing_candidate_metadata() -> None:
    """Hot-path write は任意 metadata と provenance を同時に保存する。"""

    class _Extractor:
        def extract(self, frame: WorkspaceFrame) -> tuple[MemoryCandidate, ...]:
            _ = frame
            return (
                MemoryCandidate(
                    text="明示メモ",
                    kind=MemoryKind.NOTE,
                    salience=0.8,
                    confidence=0.9,
                    reason="explicit test memory",
                    metadata={"custom": "kept"},
                ),
            )

    store = InMemoryMemoryStore()
    result = await MemoryWriteStep(store=store, extractor=_Extractor()).run(
        _build_frame("覚えて: 明示メモ")
    )
    record = store.get(MemoryId(result.written_ids[0]))
    assert record is not None
    assert record.metadata == {
        "custom": "kept",
        "candidate_source": MemoryCandidateSource.EXPLICIT_USER_REQUEST.value,
        "retention_policy": MemoryRetentionPolicy.DURABLE.value,
        "review_required": "false",
        "reason": "explicit test memory",
    }


@pytest.mark.anyio
async def test_memory_write_step_uses_actor_and_space_scope() -> None:
    """書き込まれたレコードに actor_id / space_id が含まれることを確認する。"""
    store = InMemoryMemoryStore()
    step = MemoryWriteStep(store=store)
    frame = _build_frame("覚えて: スコープテスト", actor_id="alice", space_id="space-1")

    result = await step.run(frame)

    assert len(result.written_ids) >= 1
    record = store.get(MemoryId(result.written_ids[0]))
    assert record is not None
    assert record.actor_id == ActorId("alice")
    assert record.space_id == SpaceId("space-1")


@pytest.mark.anyio
async def test_memory_write_step_deduplicates_stable_memory_id() -> None:
    """同じ内容を2回書き込んでも重複保存されず、update されることを確認する。"""
    store = InMemoryMemoryStore()
    step = MemoryWriteStep(store=store)
    frame = _build_frame("覚えて: 重複テスト")

    result1 = await step.run(frame)
    result2 = await step.run(frame)

    assert len(result1.written_ids) >= 1
    assert result1.written_ids == result2.written_ids

    all_records = list(store.filter(MemoryQuery(text="", include_archived=True)))
    matching = [r for r in all_records if "重複テスト" in r.text]
    assert len(matching) == 1


@pytest.mark.anyio
async def test_memory_write_step_skips_without_interpreted_text() -> None:
    """interpreted_input がない場合に SKIPPED になることを確認する。"""
    store = InMemoryMemoryStore()
    step = MemoryWriteStep(store=store)
    frame = _build_frame("")

    result = await step.run(frame)

    assert result.status == StepStatus.SKIPPED
    assert result.written_ids == ()


@pytest.mark.anyio
async def test_memory_write_step_rejects_by_policy() -> None:
    """ポリシーで拒否された候補は保存されず rejected_count が増えることを確認する。"""
    store = InMemoryMemoryStore()
    policy = MemoryWritePolicy()
    step = MemoryWriteStep(store=store, policy=policy)
    frame = _build_frame("remember: my password is secret123")

    result = await step.run(frame)

    assert result.rejected_count >= 1
    assert result.written_ids == ()
    assert result.status == StepStatus.SKIPPED
