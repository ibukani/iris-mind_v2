"""SQLiteMemoryCandidateReviewStore tests。"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from iris.adapters.persistence.sqlite.stores.memory_candidate_reviews import (
    SQLiteMemoryCandidateReviewStore,
)
from iris.contracts.memory import MemoryKind
from iris.contracts.memory_candidates import (
    MemoryCandidate,
    MemoryCandidateSensitivity,
    MemoryCandidateSource,
    MemoryRetentionPolicy,
)
from iris.contracts.review_candidates import (
    ReviewCandidateFilter,
    ReviewCandidateStatus,
    ReviewCandidateType,
)
from iris.core.ids import AccountId, ActorId, ObservationId, SpaceId
from iris.core.metadata import immutable_metadata
from iris.runtime.state.memory_candidates import (
    MemoryCandidateReviewId,
    MemoryCandidateReviewRecord,
    MemoryCandidateReviewStatus,
    MemoryCandidateReviewUpdate,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.anyio
_NOW = datetime(2026, 7, 1, tzinfo=UTC)
_REVIEWED = datetime(2026, 7, 2, tzinfo=UTC)


def _store(tmp_path: Path) -> SQLiteMemoryCandidateReviewStore:
    return SQLiteMemoryCandidateReviewStore(tmp_path / "state.sqlite3")


def _record(
    candidate_id: str,
    *,
    actor_id: ActorId | None = None,
    account_id: AccountId | None = None,
    space_id: SpaceId | None = None,
    idempotency_key: str | None = None,
) -> MemoryCandidateReviewRecord:
    resolved_actor_id = actor_id or ActorId("actor-1")
    resolved_account_id = account_id or AccountId("account-1")
    resolved_space_id = space_id or SpaceId("space-1")
    candidate = MemoryCandidate(
        text="ユーザーは短い返答を好む。",
        kind=MemoryKind.PREFERENCE,
        salience=0.6,
        confidence=0.7,
        source=MemoryCandidateSource.IMPLICIT_CONVERSATION,
        reason="implicit style preference",
        retention_policy=MemoryRetentionPolicy.REVIEW_REQUIRED,
        sensitivity=MemoryCandidateSensitivity.PERSONAL,
        review_required=True,
        actor_id=resolved_actor_id,
        space_id=resolved_space_id,
        source_observation_id=ObservationId("obs-1"),
        metadata=immutable_metadata(
            {
                "runtime_event_kind": "user_feedback",
                "classifier_name": "style-detector",
                "model_name": "local-style-classifier",
                "model_version": "2026-07-01",
                "confidence": "0.70",
                "reason": "implicit style preference",
                "source_event_id": "event-1",
                "scope": "actor/account/space",
            }
        ),
    )
    return MemoryCandidateReviewRecord(
        candidate_id=MemoryCandidateReviewId(candidate_id),
        candidate=candidate,
        created_at=_NOW,
        updated_at=_NOW,
        idempotency_key=idempotency_key or f"review:{candidate_id}",
        actor_id=resolved_actor_id,
        account_id=resolved_account_id,
        space_id=resolved_space_id,
        source_observation_id=ObservationId("obs-1"),
        candidate_type=ReviewCandidateType.MEMORY,
        metadata=immutable_metadata(
            {
                "background_job_id": "job-1",
                "source_event_id": "event-1",
            }
        ),
    )


async def test_add_get_and_reopen_round_trip(tmp_path: Path) -> None:
    """追加した review candidate は reopen 後も保持される。"""
    store = _store(tmp_path)
    record = await store.add(_record("candidate-1"))
    store.close()

    reopened = _store(tmp_path)
    stored = await reopened.get(record.candidate_id)

    assert stored == record
    assert stored is not None
    assert stored.candidate_type is ReviewCandidateType.MEMORY
    assert stored.candidate.metadata["runtime_event_kind"] == "user_feedback"
    assert stored.candidate.metadata["classifier_name"] == "style-detector"
    assert stored.candidate.metadata["model_version"] == "2026-07-01"
    assert stored.metadata["background_job_id"] == "job-1"
    reopened.close()


async def test_add_nowait_is_synchronous_and_persistent(tmp_path: Path) -> None:
    """同期 worker 用 add_nowait でも永続化できる。"""
    store = _store(tmp_path)
    record = store.add_nowait(_record("candidate-sync"))

    assert await store.get(record.candidate_id) == record
    store.close()


async def test_duplicate_candidate_id_and_idempotency_key_keep_first(tmp_path: Path) -> None:
    """candidate_id / idempotency_key の重複は先行 record を返す。"""
    store = _store(tmp_path)
    first = await store.add(_record("candidate-1", idempotency_key="stable-key"))
    same_id = await store.add(_record("candidate-1", idempotency_key="other-key"))
    same_key = await store.add(_record("candidate-2", idempotency_key="stable-key"))

    assert same_id == first
    assert same_key == first
    assert await store.list_pending(actor_id=ActorId("actor-2")) == ()
    store.close()


async def test_list_pending_and_status_filters(tmp_path: Path) -> None:
    """Status と actor/account/space filter は境界を守る。"""
    store = _store(tmp_path)
    first = await store.add(_record("candidate-1"))
    second = await store.add(
        _record(
            "candidate-2",
            actor_id=ActorId("actor-2"),
            account_id=AccountId("account-2"),
            space_id=SpaceId("space-2"),
        )
    )
    await store.update_status(
        second.candidate_id,
        MemoryCandidateReviewStatus.APPROVED,
        updated_at=_REVIEWED,
    )

    assert await store.list_pending(actor_id=ActorId("actor-1")) == (first,)
    assert await store.list_pending(account_id=AccountId("account-2")) == ()
    assert await store.list_pending(space_id=SpaceId("space-2")) == ()
    assert tuple(
        record.candidate_id
        for record in await store.list_by_status(
            MemoryCandidateReviewStatus.APPROVED,
            account_id=AccountId("account-2"),
        )
    ) == (second.candidate_id,)
    assert tuple(
        record.candidate_id
        for record in await store.list_by_filter(
            ReviewCandidateFilter(
                status=ReviewCandidateStatus.APPROVED,
                candidate_type=ReviewCandidateType.MEMORY,
                account_id=AccountId("account-2"),
            )
        )
    ) == (second.candidate_id,)
    store.close()


async def test_list_order_and_limit(tmp_path: Path) -> None:
    """List は created_at / candidate_id 順で limit を尊重する。"""
    store = _store(tmp_path)
    later = _record("candidate-b")
    earlier = replace(_record("candidate-a"), created_at=datetime(2026, 6, 30, tzinfo=UTC))
    await store.add(later)
    await store.add(earlier)

    listed = await store.list_pending(limit=1)

    assert listed == (earlier,)
    store.close()


async def test_update_review_persists_metadata_and_promotion(tmp_path: Path) -> None:
    """Review metadata と promoted_memory_id を保存する。"""
    store = _store(tmp_path)
    record = await store.add(_record("candidate-1"))

    updated = await store.update_review(
        record.candidate_id,
        MemoryCandidateReviewUpdate(
            status=MemoryCandidateReviewStatus.APPROVED,
            updated_at=_REVIEWED,
            reviewed_at=_REVIEWED,
            reviewed_by="operator",
            review_reason="stable preference",
            promoted_memory_id="memory-1",
        ),
    )

    assert updated is not None
    assert updated.status is MemoryCandidateReviewStatus.APPROVED
    assert updated.reviewed_at == _REVIEWED
    assert updated.reviewed_by == "operator"
    assert updated.review_reason == "stable preference"
    assert updated.promoted_memory_id == "memory-1"
    store.close()


async def test_rejected_candidate_reopens_with_classifier_metadata(tmp_path: Path) -> None:
    """Reject 後も小型 classifier 由来 metadata は suppression signal として残る。"""
    store = _store(tmp_path)
    record = await store.add(_record("candidate-1"))
    await store.update_review(
        record.candidate_id,
        MemoryCandidateReviewUpdate(
            status=MemoryCandidateReviewStatus.REJECTED,
            updated_at=_REVIEWED,
            reviewed_at=_REVIEWED,
            reviewed_by="operator",
            review_reason="noisy classifier output",
        ),
    )
    store.close()

    reopened = _store(tmp_path)
    stored = await reopened.get(record.candidate_id)

    assert stored is not None
    assert stored.status is MemoryCandidateReviewStatus.REJECTED
    assert stored.review_reason == "noisy classifier output"
    assert stored.candidate.metadata["model_name"] == "local-style-classifier"
    assert stored.candidate.metadata["source_event_id"] == "event-1"
    reopened.close()


async def test_update_missing_candidate_returns_none(tmp_path: Path) -> None:
    """存在しない candidate の更新は None を返す。"""
    store = _store(tmp_path)

    result = await store.update_status(
        MemoryCandidateReviewId("missing"),
        MemoryCandidateReviewStatus.REJECTED,
        updated_at=_REVIEWED,
    )

    assert result is None
    store.close()


@pytest.mark.parametrize("limit", [0, -1])
async def test_list_rejects_non_positive_limit(tmp_path: Path, limit: int) -> None:
    """曖昧な非正 limit は拒否する。"""
    store = _store(tmp_path)
    await store.add(_record("candidate-1"))

    with pytest.raises(ValueError, match="limit must be >= 1"):
        await store.list_pending(limit=limit)

    store.close()
