"""Memory candidate review service tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.cognitive.memory.candidates import (
    MemoryCandidate,
    MemoryCandidateSource,
    MemoryRetentionPolicy,
)
from iris.contracts.memory import MemoryKind
from iris.core.ids import AccountId, ActorId, ObservationId, SpaceId
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


async def test_approve_pending_candidate_updates_review_metadata() -> None:
    """Pending candidate can be approved and keeps review metadata."""
    store = InMemoryMemoryCandidateReviewStore()
    record = await store.add(_record("candidate-1"))
    service = MemoryCandidateReviewService(store, now=lambda: _NOW)

    result = await service.approve(
        record.candidate_id,
        reviewed_by="operator",
        reason="stable preference",
    )

    assert result.changed is True
    assert result.record.status is MemoryCandidateReviewStatus.APPROVED
    assert result.record.reviewed_at == _NOW
    assert result.record.reviewed_by == "operator"
    assert result.record.review_reason == "stable preference"
    assert await store.list_pending() == ()


async def test_reject_pending_candidate() -> None:
    """Pending candidate can be rejected."""
    store = InMemoryMemoryCandidateReviewStore()
    record = await store.add(_record("candidate-1"))
    service = MemoryCandidateReviewService(store, now=lambda: _NOW)

    result = await service.reject(record.candidate_id, reviewed_by="operator")

    assert result.changed is True
    assert result.record.status is MemoryCandidateReviewStatus.REJECTED
    assert result.record.reviewed_by == "operator"


async def test_discard_pending_candidate() -> None:
    """Pending candidate can be discarded."""
    store = InMemoryMemoryCandidateReviewStore()
    record = await store.add(_record("candidate-1"))
    service = MemoryCandidateReviewService(store, now=lambda: _NOW)

    result = await service.discard(record.candidate_id, reason="stale")

    assert result.changed is True
    assert result.record.status is MemoryCandidateReviewStatus.DISCARDED
    assert result.record.review_reason == "stale"


async def test_unknown_candidate_raises_not_found() -> None:
    """Unknown candidate id is reported explicitly."""
    service = MemoryCandidateReviewService(InMemoryMemoryCandidateReviewStore(), now=lambda: _NOW)

    with pytest.raises(MemoryCandidateNotFoundError):
        await service.approve(MemoryCandidateReviewId("missing"))


async def test_same_state_transition_is_idempotent() -> None:
    """Repeating the same review decision is idempotent."""
    store = InMemoryMemoryCandidateReviewStore()
    record = await store.add(_record("candidate-1"))
    service = MemoryCandidateReviewService(store, now=lambda: _NOW)

    first = await service.approve(record.candidate_id, reason="ok")
    second = await service.approve(record.candidate_id, reason="ignored")

    assert first.changed is True
    assert second.changed is False
    assert second.record.review_reason == "ok"


async def test_list_pending_and_status_filters_by_actor_account_and_space() -> None:
    """Review service keeps actor/account/space boundaries when listing records."""
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

    assert await service.list_pending(actor_id=ActorId("actor-1")) == (first,)
    assert await service.list_pending(account_id=AccountId("account-2")) == ()
    assert await service.list_pending(space_id=SpaceId("space-2")) == ()
    approved_second = await store.get(second.candidate_id)
    assert await service.list_by_status(
        MemoryCandidateReviewStatus.APPROVED,
        account_id=AccountId("account-2"),
    ) == (approved_second,)


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
    )
    return MemoryCandidateReviewRecord(
        candidate_id=MemoryCandidateReviewId(candidate_id),
        candidate=candidate,
        created_at=_NOW,
        updated_at=_NOW,
        idempotency_key=f"review:{candidate_id}",
        actor_id=resolved_actor_id,
        account_id=resolved_account_id,
        space_id=resolved_space_id,
        source_observation_id=ObservationId("obs-1"),
    )
