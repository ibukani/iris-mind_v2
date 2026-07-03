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
    ReviewSharedEpisodicMemoryCandidatePayload,
)
from iris.contracts.shared_episodic_memory import (
    SharedEpisodicAdmissionPolicy,
    SharedEpisodicAdmissionRisk,
    SharedEpisodicMemoryKind,
    SharedEpisodicRetrievalMetadata,
    SharedEpisodicSourceEventRef,
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
    assert detail.shared_episodic_memory_candidate is None
    assert detail.candidate_type is ReviewCandidateType.PERSONA_PATCH
    assert detail.metadata["source_event_id"] == "event-1"


def test_review_candidate_detail_supports_shared_episodic_payload() -> None:
    """Shared episodic memory は memory payload と分離した typed payload を持つ。"""
    source_event = SharedEpisodicSourceEventRef(
        source_event_id="event-1",
        observation_id=ObservationId("obs-1"),
        occurred_at=_NOW,
    )
    detail = ReviewCandidateDetail(
        candidate_id="shared-1",
        candidate_type=ReviewCandidateType.SHARED_EPISODIC_MEMORY,
        status=ReviewCandidateStatus.PENDING_REVIEW,
        scope=ReviewCandidateScope(
            actor_id=ActorId("actor-1"),
            account_id=AccountId("account-1"),
            space_id=SpaceId("space-1"),
        ),
        source_observation_id=ObservationId("obs-1"),
        shared_episodic_memory_candidate=ReviewSharedEpisodicMemoryCandidatePayload(
            summary="Iris とユーザーが初めて内輪ネタを作った。",
            kind=SharedEpisodicMemoryKind.RUNNING_JOKE,
            actor_id=ActorId("actor-1"),
            account_id=AccountId("account-1"),
            space_id=SpaceId("space-1"),
            source_events=(source_event,),
            occurred_at=_NOW,
            confidence=0.81,
            reason="同じ冗談が後続ターンで再利用されたため。",
            review_required=True,
            admission_policy=SharedEpisodicAdmissionPolicy.REVIEW_REQUIRED,
            admission_risk=SharedEpisodicAdmissionRisk.NORMAL,
            retrieval=SharedEpisodicRetrievalMetadata(
                topics=("running-joke",),
                relationship_signal="familiarity",
                salience=0.65,
            ),
            metadata=immutable_metadata({"extractor": "fixture"}),
        ),
        created_at=_NOW,
        updated_at=_NOW,
        candidate_metadata=immutable_metadata({"source_event_id": "event-1"}),
    )

    assert detail.memory_candidate is None
    assert detail.shared_episodic_memory_candidate is not None
    assert detail.shared_episodic_memory_candidate.kind is (SharedEpisodicMemoryKind.RUNNING_JOKE)
    assert detail.shared_episodic_memory_candidate.account_id == AccountId("account-1")
    assert detail.shared_episodic_memory_candidate.retrieval.topics == ("running-joke",)


def test_review_shared_episodic_payload_enforces_admission_contract() -> None:
    """Review payload 単体でも shared episodic admission policy を検証する。"""
    with pytest.raises(ValidationError):
        ReviewSharedEpisodicMemoryCandidatePayload(
            summary="共有イベント。",
            kind=SharedEpisodicMemoryKind.SHARED_EVENT,
            actor_id=ActorId("actor-1"),
            account_id=AccountId("account-1"),
            space_id=SpaceId("space-1"),
            source_events=(
                SharedEpisodicSourceEventRef(
                    source_event_id="event-1",
                    observation_id=ObservationId("obs-1"),
                    occurred_at=_NOW,
                ),
            ),
            occurred_at=_NOW,
            confidence=0.8,
            reason="共有イベント候補。",
            review_required=True,
            admission_policy=SharedEpisodicAdmissionPolicy.REJECT,
            admission_risk=SharedEpisodicAdmissionRisk.SECRET_LIKE,
            retrieval=SharedEpisodicRetrievalMetadata(),
        )


def test_review_candidate_detail_rejects_mixed_memory_and_shared_payloads() -> None:
    """Memory payload と shared episodic payload の混在を境界で拒否する。"""
    memory_payload = ReviewMemoryCandidatePayload(
        text="ユーザーは短い返答を好む。",
        kind=MemoryKind.PREFERENCE,
        salience=0.6,
        confidence=0.7,
        source=MemoryCandidateSource.IMPLICIT_CONVERSATION,
        retention_policy=MemoryRetentionPolicy.REVIEW_REQUIRED,
        sensitivity=MemoryCandidateSensitivity.NORMAL,
        review_required=True,
    )
    shared_payload = ReviewSharedEpisodicMemoryCandidatePayload(
        summary="共有イベント。",
        kind=SharedEpisodicMemoryKind.SHARED_EVENT,
        actor_id=ActorId("actor-1"),
        account_id=AccountId("account-1"),
        space_id=SpaceId("space-1"),
        source_events=(
            SharedEpisodicSourceEventRef(
                source_event_id="event-1",
                observation_id=ObservationId("obs-1"),
                occurred_at=_NOW,
            ),
        ),
        occurred_at=_NOW,
        confidence=0.8,
        reason="共有イベント候補。",
        review_required=True,
        admission_policy=SharedEpisodicAdmissionPolicy.REVIEW_REQUIRED,
        admission_risk=SharedEpisodicAdmissionRisk.NORMAL,
        retrieval=SharedEpisodicRetrievalMetadata(),
    )

    with pytest.raises(ValidationError):
        ReviewCandidateDetail(
            candidate_id="shared-1",
            candidate_type=ReviewCandidateType.SHARED_EPISODIC_MEMORY,
            status=ReviewCandidateStatus.PENDING_REVIEW,
            scope=ReviewCandidateScope(actor_id=ActorId("actor-1")),
            memory_candidate=memory_payload,
            shared_episodic_memory_candidate=shared_payload,
            created_at=_NOW,
            updated_at=_NOW,
        )

    with pytest.raises(ValidationError):
        ReviewCandidateDetail(
            candidate_id="shared-2",
            candidate_type=ReviewCandidateType.SHARED_EPISODIC_MEMORY,
            status=ReviewCandidateStatus.PENDING_REVIEW,
            scope=ReviewCandidateScope(actor_id=ActorId("actor-1")),
            created_at=_NOW,
            updated_at=_NOW,
        )


def test_review_candidate_detail_rejects_unmatched_payload_for_future_type() -> None:
    """Future candidate type に既存 typed payload を誤って混ぜない。"""
    memory_payload = ReviewMemoryCandidatePayload(
        text="ユーザーは短い返答を好む。",
        kind=MemoryKind.PREFERENCE,
        salience=0.6,
        confidence=0.7,
        source=MemoryCandidateSource.IMPLICIT_CONVERSATION,
        retention_policy=MemoryRetentionPolicy.REVIEW_REQUIRED,
        sensitivity=MemoryCandidateSensitivity.NORMAL,
        review_required=True,
    )

    with pytest.raises(ValidationError):
        ReviewCandidateDetail(
            candidate_id="persona-1",
            candidate_type=ReviewCandidateType.PERSONA_PATCH,
            status=ReviewCandidateStatus.PENDING_REVIEW,
            scope=ReviewCandidateScope(actor_id=ActorId("actor-1")),
            memory_candidate=memory_payload,
            created_at=_NOW,
            updated_at=_NOW,
        )


def test_review_candidate_detail_rejects_shared_episodic_scope_mismatch() -> None:
    """Shared episodic payload は review scope と同じ actor/account/space 境界を持つ。"""
    shared_payload = ReviewSharedEpisodicMemoryCandidatePayload(
        summary="共有イベント。",
        kind=SharedEpisodicMemoryKind.SHARED_EVENT,
        actor_id=ActorId("actor-1"),
        account_id=AccountId("account-1"),
        space_id=SpaceId("space-1"),
        source_events=(
            SharedEpisodicSourceEventRef(
                source_event_id="event-1",
                observation_id=ObservationId("obs-1"),
                occurred_at=_NOW,
            ),
        ),
        occurred_at=_NOW,
        confidence=0.8,
        reason="共有イベント候補。",
        review_required=True,
        admission_policy=SharedEpisodicAdmissionPolicy.REVIEW_REQUIRED,
        admission_risk=SharedEpisodicAdmissionRisk.NORMAL,
        retrieval=SharedEpisodicRetrievalMetadata(),
    )

    with pytest.raises(ValidationError):
        ReviewCandidateDetail(
            candidate_id="shared-1",
            candidate_type=ReviewCandidateType.SHARED_EPISODIC_MEMORY,
            status=ReviewCandidateStatus.PENDING_REVIEW,
            scope=ReviewCandidateScope(
                actor_id=ActorId("actor-1"),
                account_id=AccountId("other-account"),
                space_id=SpaceId("space-1"),
            ),
            source_observation_id=ObservationId("obs-1"),
            shared_episodic_memory_candidate=shared_payload,
            created_at=_NOW,
            updated_at=_NOW,
        )


def test_review_candidate_detail_rejects_shared_episodic_source_mismatch() -> None:
    """Detail の source_observation_id は shared episodic source event を参照する。"""
    shared_payload = ReviewSharedEpisodicMemoryCandidatePayload(
        summary="共有イベント。",
        kind=SharedEpisodicMemoryKind.SHARED_EVENT,
        actor_id=ActorId("actor-1"),
        account_id=AccountId("account-1"),
        space_id=SpaceId("space-1"),
        source_events=(
            SharedEpisodicSourceEventRef(
                source_event_id="event-1",
                observation_id=ObservationId("obs-1"),
                occurred_at=_NOW,
            ),
        ),
        occurred_at=_NOW,
        confidence=0.8,
        reason="共有イベント候補。",
        review_required=True,
        admission_policy=SharedEpisodicAdmissionPolicy.REVIEW_REQUIRED,
        admission_risk=SharedEpisodicAdmissionRisk.NORMAL,
        retrieval=SharedEpisodicRetrievalMetadata(),
    )

    with pytest.raises(ValidationError):
        ReviewCandidateDetail(
            candidate_id="shared-1",
            candidate_type=ReviewCandidateType.SHARED_EPISODIC_MEMORY,
            status=ReviewCandidateStatus.PENDING_REVIEW,
            scope=ReviewCandidateScope(
                actor_id=ActorId("actor-1"),
                account_id=AccountId("account-1"),
                space_id=SpaceId("space-1"),
            ),
            source_observation_id=ObservationId("obs-other"),
            shared_episodic_memory_candidate=shared_payload,
            created_at=_NOW,
            updated_at=_NOW,
        )


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
