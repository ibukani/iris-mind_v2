"""Approved implicit memory candidate promotion tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.cognitive.memory.candidates import (
    MemoryCandidate,
    MemoryCandidateSensitivity,
    MemoryCandidateSource,
    MemoryRetentionPolicy,
)
from iris.contracts.memory import MemoryKind, MemoryQuery
from iris.core.ids import ActorId, ObservationId, SpaceId
from iris.runtime.learning.review_promotion import (
    ApprovedMemoryCandidatePromoter,
    MemoryCandidatePromotionNotFoundError,
)
from iris.runtime.learning.review_service import MemoryCandidateReviewService
from iris.runtime.state.memory_candidates import (
    InMemoryMemoryCandidateReviewStore,
    MemoryCandidateReviewId,
    MemoryCandidateReviewRecord,
    MemoryCandidateReviewStatus,
)

pytestmark = pytest.mark.anyio

_NOW = datetime(2026, 7, 1, tzinfo=UTC)
_PROMOTED_AT = datetime(2026, 7, 1, 1, tzinfo=UTC)


async def test_approved_candidate_promotes_to_memory_store() -> None:
    """Approved implicit candidate is promoted to canonical MemoryStore."""
    store = InMemoryMemoryCandidateReviewStore()
    memory_store = InMemoryMemoryStore()
    record = await store.add(_record("candidate-1"))
    await MemoryCandidateReviewService(store, now=lambda: _NOW).approve(
        record.candidate_id,
        reviewed_by="operator",
        reason="stable preference",
    )
    promoter = ApprovedMemoryCandidatePromoter(store, memory_store, now=lambda: _PROMOTED_AT)

    result = await promoter.promote(record.candidate_id)

    assert result.promoted is True
    assert result.memory is not None
    assert result.memory.text == "ユーザーは短い返答を好む。"
    assert result.memory.actor_id == ActorId("actor-1")
    assert result.memory.space_id == SpaceId("space-1")
    assert result.memory.source_observation_id == ObservationId("obs-1")
    assert result.memory.created_at == _PROMOTED_AT
    assert (
        result.memory.metadata["candidate_source"]
        == MemoryCandidateSource.IMPLICIT_CONVERSATION.value
    )
    assert (
        result.memory.metadata["original_retention_policy"]
        == MemoryRetentionPolicy.REVIEW_REQUIRED.value
    )
    assert result.memory.metadata["review_status"] == MemoryCandidateReviewStatus.APPROVED.value
    assert result.memory.metadata["reviewed_by"] == "operator"
    assert result.memory.metadata["review_reason"] == "stable preference"
    assert result.memory.metadata["reason"] == "implicit style preference"
    assert result.memory.metadata["confidence"] == "0.6"
    assert result.record.promoted_memory_id == str(result.memory.id)
    assert memory_store.get(result.memory.id) == result.memory


async def test_pending_rejected_and_discarded_candidates_do_not_promote() -> None:
    """Only approved candidates can be promoted."""
    store = InMemoryMemoryCandidateReviewStore()
    memory_store = InMemoryMemoryStore()
    pending = await store.add(_record("candidate-pending"))
    rejected = await store.add(_record("candidate-rejected"))
    discarded = await store.add(_record("candidate-discarded"))
    service = MemoryCandidateReviewService(store, now=lambda: _NOW)
    await service.reject(rejected.candidate_id)
    await service.discard(discarded.candidate_id)
    promoter = ApprovedMemoryCandidatePromoter(store, memory_store, now=lambda: _PROMOTED_AT)

    results = (
        await promoter.promote(pending.candidate_id),
        await promoter.promote(rejected.candidate_id),
        await promoter.promote(discarded.candidate_id),
    )

    assert all(not result.promoted for result in results)
    assert all(result.memory is None for result in results)
    assert memory_store.search(MemoryQuery(text="短い返答", limit=10)) == ()


async def test_promotion_is_idempotent() -> None:
    """Repeated promotion does not create another memory record."""
    store = InMemoryMemoryCandidateReviewStore()
    memory_store = InMemoryMemoryStore()
    record = await store.add(_record("candidate-1"))
    await MemoryCandidateReviewService(store, now=lambda: _NOW).approve(record.candidate_id)
    promoter = ApprovedMemoryCandidatePromoter(store, memory_store, now=lambda: _PROMOTED_AT)

    first = await promoter.promote(record.candidate_id)
    second = await promoter.promote(record.candidate_id)

    assert first.promoted is True
    assert second.promoted is False
    assert second.reason == "already_promoted"
    assert first.memory is not None
    assert second.memory == first.memory
    assert len(memory_store.filter(MemoryQuery(text="", limit=10))) == 1


async def test_unknown_candidate_promotion_raises_not_found() -> None:
    """Unknown candidate id is reported explicitly."""
    promoter = ApprovedMemoryCandidatePromoter(
        InMemoryMemoryCandidateReviewStore(),
        InMemoryMemoryStore(),
        now=lambda: _PROMOTED_AT,
    )

    with pytest.raises(MemoryCandidatePromotionNotFoundError):
        await promoter.promote(MemoryCandidateReviewId("missing"))


async def test_secret_like_candidate_is_rejected_by_promotion_policy() -> None:
    """Even approved credential-like candidates are not promoted."""
    store = InMemoryMemoryCandidateReviewStore()
    memory_store = InMemoryMemoryStore()
    record = await store.add(
        _record(
            "candidate-secret",
            candidate=replace(
                _candidate(),
                text="API key is sk-test-1234567890abcdef",
                sensitivity=MemoryCandidateSensitivity.SECRET_LIKE,
            ),
        )
    )
    await MemoryCandidateReviewService(store, now=lambda: _NOW).approve(record.candidate_id)
    promoter = ApprovedMemoryCandidatePromoter(store, memory_store, now=lambda: _PROMOTED_AT)

    result = await promoter.promote(record.candidate_id)

    assert result.promoted is False
    assert result.reason == "candidate_rejected_by_promotion_policy"
    assert result.memory is None
    assert memory_store.search(MemoryQuery(text="sk-test", limit=10)) == ()


async def test_sensitive_profile_candidate_is_rejected_by_promotion_policy() -> None:
    """Sensitive profile text is not promoted by default."""
    store = InMemoryMemoryCandidateReviewStore()
    memory_store = InMemoryMemoryStore()
    record = await store.add(
        _record(
            "candidate-sensitive",
            candidate=replace(
                _candidate(),
                text="ユーザーはADHDについて話した。",
                sensitivity=MemoryCandidateSensitivity.SENSITIVE,
            ),
        )
    )
    await MemoryCandidateReviewService(store, now=lambda: _NOW).approve(record.candidate_id)
    promoter = ApprovedMemoryCandidatePromoter(store, memory_store, now=lambda: _PROMOTED_AT)

    result = await promoter.promote(record.candidate_id)

    assert result.promoted is False
    assert result.reason == "candidate_rejected_by_promotion_policy"
    assert result.memory is None
    assert memory_store.search(MemoryQuery(text="ADHD", limit=10)) == ()


async def test_credential_like_normal_candidate_is_rejected_by_promotion_policy() -> None:
    """Credential-like text is rejected even when sensitivity metadata is wrong."""
    store = InMemoryMemoryCandidateReviewStore()
    memory_store = InMemoryMemoryStore()
    record = await store.add(
        _record(
            "candidate-credential",
            candidate=replace(
                _candidate(),
                text="ユーザーのトークンは sk-test-1234567890abcdef",
                sensitivity=MemoryCandidateSensitivity.NORMAL,
            ),
        )
    )
    await MemoryCandidateReviewService(store, now=lambda: _NOW).approve(record.candidate_id)
    promoter = ApprovedMemoryCandidatePromoter(store, memory_store, now=lambda: _PROMOTED_AT)

    result = await promoter.promote(record.candidate_id)

    assert result.promoted is False
    assert result.reason == "candidate_rejected_by_promotion_policy"
    assert result.memory is None
    assert memory_store.search(MemoryQuery(text="sk-test", limit=10)) == ()


async def test_low_confidence_candidate_is_rejected_by_promotion_policy() -> None:
    """Approved candidate below confidence threshold is not promoted."""
    store = InMemoryMemoryCandidateReviewStore()
    memory_store = InMemoryMemoryStore()
    record = await store.add(
        _record("candidate-low-confidence", candidate=replace(_candidate(), confidence=0.2))
    )
    await MemoryCandidateReviewService(store, now=lambda: _NOW).approve(record.candidate_id)
    promoter = ApprovedMemoryCandidatePromoter(store, memory_store, now=lambda: _PROMOTED_AT)

    result = await promoter.promote(record.candidate_id)

    assert result.promoted is False
    assert result.reason == "candidate_rejected_by_promotion_policy"
    assert result.memory is None
    assert memory_store.filter(MemoryQuery(text="", limit=10)) == ()


async def test_non_implicit_candidate_is_rejected_by_promotion_policy() -> None:
    """Promotion requires implicit-conversation review-required provenance."""
    store = InMemoryMemoryCandidateReviewStore()
    memory_store = InMemoryMemoryStore()
    record = await store.add(
        _record(
            "candidate-explicit",
            candidate=replace(
                _candidate(),
                source=MemoryCandidateSource.EXPLICIT_USER_REQUEST,
                retention_policy=MemoryRetentionPolicy.DURABLE,
                review_required=False,
            ),
        )
    )
    await MemoryCandidateReviewService(store, now=lambda: _NOW).approve(record.candidate_id)
    promoter = ApprovedMemoryCandidatePromoter(store, memory_store, now=lambda: _PROMOTED_AT)

    result = await promoter.promote(record.candidate_id)

    assert result.promoted is False
    assert result.reason == "candidate_rejected_by_promotion_policy"
    assert result.memory is None
    assert memory_store.filter(MemoryQuery(text="", limit=10)) == ()


def _record(
    candidate_id: str,
    *,
    candidate: MemoryCandidate | None = None,
) -> MemoryCandidateReviewRecord:
    return MemoryCandidateReviewRecord(
        candidate_id=MemoryCandidateReviewId(candidate_id),
        candidate=candidate or _candidate(),
        created_at=_NOW,
        updated_at=_NOW,
        idempotency_key=f"review:{candidate_id}",
        actor_id=ActorId("actor-1"),
        space_id=SpaceId("space-1"),
        source_observation_id=ObservationId("obs-1"),
    )


def _candidate() -> MemoryCandidate:
    return MemoryCandidate(
        text="ユーザーは短い返答を好む。",
        kind=MemoryKind.PREFERENCE,
        salience=0.6,
        confidence=0.6,
        source=MemoryCandidateSource.IMPLICIT_CONVERSATION,
        reason="implicit style preference",
        retention_policy=MemoryRetentionPolicy.REVIEW_REQUIRED,
        sensitivity=MemoryCandidateSensitivity.NORMAL,
        review_required=True,
        actor_id=ActorId("actor-1"),
        space_id=SpaceId("space-1"),
        source_observation_id=ObservationId("obs-1"),
    )
