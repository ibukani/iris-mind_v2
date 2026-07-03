"""Review candidate contract tests。"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import ValidationError
import pytest

from iris.contracts.memory import MemoryKind
from iris.contracts.memory_candidates import (
    MemoryCandidateSensitivity,
    MemoryCandidateSource,
    MemoryRetentionPolicy,
)
from iris.contracts.review_candidates import (
    ReviewCandidateDetail,
    ReviewCandidateFilter,
    ReviewCandidateScope,
    ReviewCandidateStatus,
    ReviewCandidateSummary,
    ReviewCandidateType,
    ReviewDecisionKind,
    ReviewDecisionResult,
    ReviewMemoryCandidatePayload,
)
from iris.core.ids import AccountId, ActorId, ObservationId, SpaceId
from iris.core.metadata import immutable_metadata

_NOW = datetime(2026, 7, 1, tzinfo=UTC)


def test_review_candidate_filter_defaults_to_pending_review() -> None:
    """Review list filter は pending review を既定にする。"""
    query = ReviewCandidateFilter(actor_id=ActorId("actor-1"))

    assert query.status is ReviewCandidateStatus.PENDING_REVIEW
    assert query.candidate_type is None
    assert query.actor_id == ActorId("actor-1")
    assert query.limit == 50


@pytest.mark.parametrize("limit", [0, -1])
def test_review_candidate_filter_rejects_non_positive_limit(limit: int) -> None:
    """List filter は非正 limit を契約境界で拒否する。"""
    with pytest.raises(ValidationError):
        ReviewCandidateFilter(limit=limit)


def test_review_candidate_summary_preserves_scope_and_metadata() -> None:
    """Summary DTO は候補種別、scope、classifier metadata を保持する。"""
    summary = ReviewCandidateSummary(
        candidate_id="candidate-1",
        candidate_type=ReviewCandidateType.MEMORY,
        status=ReviewCandidateStatus.PENDING_REVIEW,
        scope=ReviewCandidateScope(
            actor_id=ActorId("actor-1"),
            account_id=AccountId("account-1"),
            space_id=SpaceId("space-1"),
        ),
        source_observation_id=ObservationId("obs-1"),
        text_preview="ユーザーは短い返答を好む。",
        confidence=0.8,
        reason="classifier accepted",
        created_at=_NOW,
        updated_at=_NOW,
        metadata=immutable_metadata({"background_job_id": "job-1"}),
        candidate_metadata=immutable_metadata(
            {
                "classifier_name": "style-detector",
                "model_version": "2026-07-01",
            }
        ),
    )

    assert summary.candidate_type is ReviewCandidateType.MEMORY
    assert summary.scope.account_id == AccountId("account-1")
    assert summary.metadata["background_job_id"] == "job-1"
    assert summary.candidate_metadata["classifier_name"] == "style-detector"


def test_review_candidate_detail_supports_future_candidate_type_without_memory_payload() -> None:
    """Memory payload なしの future candidate type でも contract を壊さない。"""
    detail = ReviewCandidateDetail(
        candidate_id="persona-1",
        candidate_type=ReviewCandidateType.PERSONA_PATCH,
        status=ReviewCandidateStatus.PENDING_REVIEW,
        scope=ReviewCandidateScope(actor_id=ActorId("actor-1")),
        created_at=_NOW,
        updated_at=_NOW,
        metadata=immutable_metadata({"source_event_id": "event-1"}),
    )

    assert detail.memory_candidate is None
    assert detail.candidate_type is ReviewCandidateType.PERSONA_PATCH
    assert detail.metadata["source_event_id"] == "event-1"


def test_review_decision_result_contains_boundary_detail_not_store_record() -> None:
    """Decision result は service boundary DTO を返す。"""
    detail = ReviewCandidateDetail(
        candidate_id="candidate-1",
        candidate_type=ReviewCandidateType.MEMORY,
        status=ReviewCandidateStatus.APPROVED,
        scope=ReviewCandidateScope(actor_id=ActorId("actor-1")),
        memory_candidate=ReviewMemoryCandidatePayload(
            text="ユーザーは短い返答を好む。",
            kind=MemoryKind.PREFERENCE,
            salience=0.6,
            confidence=0.7,
            source=MemoryCandidateSource.IMPLICIT_CONVERSATION,
            retention_policy=MemoryRetentionPolicy.REVIEW_REQUIRED,
            sensitivity=MemoryCandidateSensitivity.NORMAL,
            review_required=True,
        ),
        created_at=_NOW,
        updated_at=_NOW,
    )

    result = ReviewDecisionResult(
        candidate=detail,
        decision=ReviewDecisionKind.APPROVE,
        changed=True,
    )

    assert result.candidate.status is ReviewCandidateStatus.APPROVED
    assert result.decision is ReviewDecisionKind.APPROVE
