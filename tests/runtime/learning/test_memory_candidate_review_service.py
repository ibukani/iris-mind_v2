"""Memory candidate review service tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from iris.contracts.memory import MemoryKind
from iris.contracts.memory_candidates import (
    MemoryCandidate,
    MemoryCandidateSource,
    MemoryRetentionPolicy,
)
from iris.contracts.review_candidates import (
    ReviewCandidateFilter,
    ReviewCandidateStatus,
    ReviewCandidateType,
    ReviewDecisionKind,
    ReviewDecisionRequest,
)
from iris.core.ids import AccountId, ActorId, ObservationId, SpaceId
from iris.core.metadata import immutable_metadata
from iris.runtime.learning.review_service import (
    InvalidMemoryCandidateReviewTransitionError,
    MemoryCandidateNotFoundError,
    MemoryCandidateReviewService,
)
from iris.runtime.state.memory_candidates import (
    InMemoryMemoryCandidateReviewStore,
    MemoryCandidateReviewId,
    MemoryCandidateReviewRecord,
    MemoryCandidateReviewStatus,
)

pytestmark = pytest.mark.anyio

_NOW = datetime(2026, 7, 1, tzinfo=UTC)


async def test_read_pending_candidate_returns_boundary_detail() -> None:
    """Pending candidate は service boundary DTO として read できる。"""
    store = InMemoryMemoryCandidateReviewStore()
    record = await store.add(_record("candidate-1"))
    service = MemoryCandidateReviewService(store, now=lambda: _NOW)

    detail = await service.read(record.candidate_id)

    assert detail.candidate_id == "candidate-1"
    assert detail.candidate_type is ReviewCandidateType.MEMORY
    assert detail.status is ReviewCandidateStatus.PENDING_REVIEW
    assert detail.scope.actor_id == ActorId("actor-1")
    assert detail.scope.account_id == AccountId("account-1")
    assert detail.scope.space_id == SpaceId("space-1")
    assert detail.memory_candidate is not None
    assert detail.memory_candidate.text == record.candidate.text
    assert detail.memory_candidate.kind is record.candidate.kind
    assert detail.candidate_metadata["classifier_name"] == "style-detector"
    assert detail.metadata["source_event_id"] == "event-1"


async def test_approve_pending_candidate_updates_review_metadata() -> None:
    """Pending candidate can be approved and keeps review metadata."""
    store = InMemoryMemoryCandidateReviewStore()
    record = await store.add(_record("candidate-1"))
    service = MemoryCandidateReviewService(store, now=lambda: _NOW)

    result = await service.approve(
        record.candidate_id,
        ReviewDecisionRequest(reviewed_by="operator", reason="stable preference"),
    )

    assert result.changed is True
    assert result.decision is ReviewDecisionKind.APPROVE
    assert result.candidate.status is ReviewCandidateStatus.APPROVED
    assert result.candidate.reviewed_at == _NOW
    assert result.candidate.reviewed_by == "operator"
    assert result.candidate.review_reason == "stable preference"
    assert await store.list_pending() == ()


async def test_reject_pending_candidate() -> None:
    """Pending candidate can be rejected."""
    store = InMemoryMemoryCandidateReviewStore()
    record = await store.add(_record("candidate-1"))
    service = MemoryCandidateReviewService(store, now=lambda: _NOW)

    result = await service.reject(
        record.candidate_id,
        ReviewDecisionRequest(reviewed_by="operator"),
    )

    assert result.changed is True
    assert result.decision is ReviewDecisionKind.REJECT
    assert result.candidate.status is ReviewCandidateStatus.REJECTED
    assert result.candidate.reviewed_by == "operator"


async def test_discard_pending_candidate() -> None:
    """Pending candidate can be discarded."""
    store = InMemoryMemoryCandidateReviewStore()
    record = await store.add(_record("candidate-1"))
    service = MemoryCandidateReviewService(store, now=lambda: _NOW)

    result = await service.discard(
        record.candidate_id,
        ReviewDecisionRequest(reason="stale"),
    )

    assert result.changed is True
    assert result.decision is ReviewDecisionKind.DISCARD
    assert result.candidate.status is ReviewCandidateStatus.DISCARDED
    assert result.candidate.review_reason == "stale"


async def test_unknown_candidate_raises_not_found() -> None:
    """Unknown candidate id is reported explicitly."""
    service = MemoryCandidateReviewService(InMemoryMemoryCandidateReviewStore(), now=lambda: _NOW)

    with pytest.raises(MemoryCandidateNotFoundError):
        await service.approve(MemoryCandidateReviewId("missing"))
    with pytest.raises(MemoryCandidateNotFoundError):
        await service.read(MemoryCandidateReviewId("missing"))


async def test_same_state_transition_is_idempotent() -> None:
    """Repeating the same review decision is idempotent."""
    store = InMemoryMemoryCandidateReviewStore()
    record = await store.add(_record("candidate-1"))
    service = MemoryCandidateReviewService(store, now=lambda: _NOW)

    first = await service.approve(
        record.candidate_id,
        ReviewDecisionRequest(reason="ok"),
    )
    second = await service.approve(
        record.candidate_id,
        ReviewDecisionRequest(reason="ignored"),
    )

    assert first.changed is True
    assert second.changed is False
    assert second.candidate.review_reason == "ok"


async def test_list_candidates_filters_by_status_actor_account_space_and_type() -> None:
    """Review service keeps status/type/actor/account/space boundaries when listing."""
    store = InMemoryMemoryCandidateReviewStore()
    first = await store.add(_record("candidate-1"))
    second = await store.add(
        _record(
            "candidate-2",
            actor_id=ActorId("actor-2"),
            account_id=AccountId("account-2"),
            space_id=SpaceId("space-2"),
        )
    )
    service = MemoryCandidateReviewService(store, now=lambda: _NOW)
    await service.approve(second.candidate_id)

    pending_actor = await service.list_candidates(
        ReviewCandidateFilter(actor_id=ActorId("actor-1"))
    )
    pending_other_account = await service.list_candidates(
        ReviewCandidateFilter(account_id=AccountId("account-2"))
    )
    approved_other_account = await service.list_candidates(
        ReviewCandidateFilter(
            status=ReviewCandidateStatus.APPROVED,
            candidate_type=ReviewCandidateType.MEMORY,
            account_id=AccountId("account-2"),
        )
    )

    assert tuple(summary.candidate_id for summary in pending_actor) == (str(first.candidate_id),)
    assert pending_other_account == ()
    assert tuple(summary.candidate_id for summary in approved_other_account) == (
        str(second.candidate_id),
    )


async def test_list_candidates_can_return_all_statuses() -> None:
    """Status=None の filter は lifecycle 横断 list に使える。"""
    store = InMemoryMemoryCandidateReviewStore()
    first = await store.add(_record("candidate-1"))
    second = await store.add(_record("candidate-2"))
    service = MemoryCandidateReviewService(store, now=lambda: _NOW)
    await service.reject(second.candidate_id)

    listed = await service.list_candidates(ReviewCandidateFilter(status=None))

    assert tuple(summary.candidate_id for summary in listed) == (
        str(first.candidate_id),
        str(second.candidate_id),
    )


async def test_rejected_candidate_keeps_metadata_for_future_suppression_signal() -> None:
    """Rejected candidate は classifier metadata と review reason を保持する。"""
    store = InMemoryMemoryCandidateReviewStore()
    record = await store.add(_record("candidate-1"))
    service = MemoryCandidateReviewService(store, now=lambda: _NOW)

    result = await service.reject(
        record.candidate_id,
        ReviewDecisionRequest(reviewed_by="operator", reason="noisy classifier output"),
    )
    detail = await service.read(record.candidate_id)

    assert result.candidate.status is ReviewCandidateStatus.REJECTED
    assert detail.review_reason == "noisy classifier output"
    assert detail.candidate_metadata["model_name"] == "local-style-classifier"
    assert detail.metadata["source_event_id"] == "event-1"


@pytest.mark.parametrize("limit", [0, -1])
async def test_list_methods_reject_non_positive_limit(limit: int) -> None:
    """Review listing rejects ambiguous non-positive limits."""
    store = InMemoryMemoryCandidateReviewStore()
    await store.add(_record("candidate-1"))
    service = MemoryCandidateReviewService(store, now=lambda: _NOW)

    with pytest.raises(ValueError, match="limit must be >= 1"):
        await service.list_candidates(ReviewCandidateFilter.model_construct(limit=limit))


async def test_rejected_candidate_cannot_be_approved() -> None:
    """Rejected candidate cannot later become approved."""
    store = InMemoryMemoryCandidateReviewStore()
    record = await store.add(_record("candidate-1"))
    service = MemoryCandidateReviewService(store, now=lambda: _NOW)

    await service.reject(record.candidate_id)

    with pytest.raises(InvalidMemoryCandidateReviewTransitionError):
        await service.approve(record.candidate_id)


async def test_discarded_candidate_cannot_be_approved() -> None:
    """Discarded candidate cannot later become approved."""
    store = InMemoryMemoryCandidateReviewStore()
    record = await store.add(_record("candidate-1"))
    service = MemoryCandidateReviewService(store, now=lambda: _NOW)

    await service.discard(record.candidate_id)

    with pytest.raises(InvalidMemoryCandidateReviewTransitionError):
        await service.approve(record.candidate_id)


async def test_approved_candidate_cannot_be_rejected_or_discarded() -> None:
    """Approved candidate lifecycle cannot be reversed."""
    store = InMemoryMemoryCandidateReviewStore()
    record = await store.add(_record("candidate-1"))
    service = MemoryCandidateReviewService(store, now=lambda: _NOW)

    await service.approve(record.candidate_id)

    with pytest.raises(InvalidMemoryCandidateReviewTransitionError):
        await service.reject(record.candidate_id)
    with pytest.raises(InvalidMemoryCandidateReviewTransitionError):
        await service.discard(record.candidate_id)


async def test_approve_only_updates_review_state_and_does_not_promote() -> None:
    """Review service は promotion workflow を直接実行しない。"""
    store = InMemoryMemoryCandidateReviewStore()
    record = await store.add(_record("candidate-1"))
    service = MemoryCandidateReviewService(store, now=lambda: _NOW)

    result = await service.approve(record.candidate_id)
    stored = await store.get(record.candidate_id)

    assert result.candidate.promoted_memory_id is None
    assert stored is not None
    assert stored.status is MemoryCandidateReviewStatus.APPROVED
    assert stored.promoted_memory_id is None


async def test_add_same_candidate_id_with_different_idempotency_key_keeps_first_record() -> None:
    """candidate_id collision keeps the first record instead of overwriting it."""
    store = InMemoryMemoryCandidateReviewStore()
    first = await store.add(_record("candidate-1"))
    second = await store.add(
        replace(
            _record(
                "candidate-1",
                actor_id=ActorId("actor-2"),
                account_id=AccountId("account-2"),
                space_id=SpaceId("space-2"),
            ),
            idempotency_key="review:other-key",
        )
    )

    stored = await store.get(first.candidate_id)

    assert second == first
    assert stored == first
    assert stored is not None
    assert stored.idempotency_key == "review:candidate-1"
    assert stored.candidate.text == "ユーザーは短い返答を好む。"
    assert await store.list_pending(actor_id=ActorId("actor-2")) == ()


def _record(
    candidate_id: str,
    *,
    actor_id: ActorId | None = None,
    account_id: AccountId | None = None,
    space_id: SpaceId | None = None,
) -> MemoryCandidateReviewRecord:
    resolved_actor_id = actor_id or ActorId("actor-1")
    resolved_account_id = account_id or AccountId("account-1")
    resolved_space_id = space_id or SpaceId("space-1")
    candidate = MemoryCandidate(
        text="ユーザーは短い返答を好む。",
        kind=MemoryKind.PREFERENCE,
        salience=0.6,
        confidence=0.6,
        source=MemoryCandidateSource.IMPLICIT_CONVERSATION,
        reason="implicit style preference",
        retention_policy=MemoryRetentionPolicy.REVIEW_REQUIRED,
        review_required=True,
        actor_id=resolved_actor_id,
        space_id=resolved_space_id,
        source_observation_id=ObservationId("obs-1"),
        metadata=immutable_metadata(
            {
                "classifier_name": "style-detector",
                "model_name": "local-style-classifier",
                "model_version": "2026-07-01",
                "confidence": "0.60",
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
        idempotency_key=f"review:{candidate_id}",
        candidate_type=ReviewCandidateType.MEMORY,
        actor_id=resolved_actor_id,
        account_id=resolved_account_id,
        space_id=resolved_space_id,
        source_observation_id=ObservationId("obs-1"),
        metadata=immutable_metadata({"source_event_id": "event-1"}),
    )
