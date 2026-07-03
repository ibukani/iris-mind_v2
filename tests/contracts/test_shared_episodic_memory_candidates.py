"""共有エピソード記憶候補 contract tests。"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import ValidationError
import pytest

from iris.contracts.shared_episodic_memory import (
    SharedEpisodicAdmissionPolicy,
    SharedEpisodicAdmissionRisk,
    SharedEpisodicMemoryCandidate,
    SharedEpisodicMemoryKind,
    SharedEpisodicRetrievalMetadata,
    SharedEpisodicSourceEventRef,
)
from iris.core.ids import AccountId, ActorId, ObservationId, SpaceId
from iris.core.metadata import immutable_metadata
from tests.helpers.approx import approx

_NOW = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)
_LATER = datetime(2026, 7, 3, 12, 5, tzinfo=UTC)


EXPECTED_KINDS = {
    "shared_event",
    "running_joke",
    "companion_milestone",
    "user_helped_iris_or_iris_helped_user",
    "conflict_and_repair",
    "memorable_failure_or_teasing",
    "recurring_topic_with_emotion",
}


def _source_event(source_event_id: str = "event-1") -> SharedEpisodicSourceEventRef:
    return SharedEpisodicSourceEventRef(
        source_event_id=source_event_id,
        observation_id=ObservationId(f"obs-{source_event_id}"),
        occurred_at=_NOW,
    )


def _candidate(
    *,
    kind: SharedEpisodicMemoryKind = SharedEpisodicMemoryKind.SHARED_EVENT,
    admission_risk: SharedEpisodicAdmissionRisk = SharedEpisodicAdmissionRisk.NORMAL,
    admission_policy: SharedEpisodicAdmissionPolicy = (
        SharedEpisodicAdmissionPolicy.REVIEW_REQUIRED
    ),
    review_required: bool = True,
    source_events: tuple[SharedEpisodicSourceEventRef, ...] = (_source_event(),),
) -> SharedEpisodicMemoryCandidate:
    return SharedEpisodicMemoryCandidate(
        summary="初めて一緒にローカルLLMの起動問題を切り分けた。",
        kind=kind,
        actor_id=ActorId("actor-1"),
        account_id=AccountId("account-1"),
        space_id=SpaceId("space-1"),
        source_events=source_events,
        occurred_at=_LATER,
        confidence=0.82,
        reason="複数ターンで共有体験として言及されたため。",
        review_required=review_required,
        admission_policy=admission_policy,
        admission_risk=admission_risk,
        retrieval=SharedEpisodicRetrievalMetadata(
            topics=("local-llm", "debugging"),
            emotional_context="達成感",
            relationship_signal="collaboration",
            salience=0.7,
        ),
        metadata=immutable_metadata({"extractor": "fixture"}),
    )


def test_companion_specific_kinds_are_explicitly_defined() -> None:
    """Issue #109 で要求された companion-specific 種別を列挙する。"""
    assert {kind.value for kind in SharedEpisodicMemoryKind} == EXPECTED_KINDS


@pytest.mark.parametrize(
    "kind",
    [
        SharedEpisodicMemoryKind.SHARED_EVENT,
        SharedEpisodicMemoryKind.RUNNING_JOKE,
        SharedEpisodicMemoryKind.COMPANION_MILESTONE,
        SharedEpisodicMemoryKind.HELP_EXCHANGE,
        SharedEpisodicMemoryKind.CONFLICT_AND_REPAIR,
        SharedEpisodicMemoryKind.MEMORABLE_FAILURE_OR_TEASING,
        SharedEpisodicMemoryKind.RECURRING_TOPIC_WITH_EMOTION,
    ],
)
def test_candidate_supports_all_shared_episodic_kinds(
    kind: SharedEpisodicMemoryKind,
) -> None:
    """各 companion-specific 種別で同じ provenance contract を使える。"""
    candidate = _candidate(kind=kind)

    assert candidate.kind is kind
    assert candidate.actor_id == ActorId("actor-1")
    assert candidate.account_id == AccountId("account-1")
    assert candidate.space_id == SpaceId("space-1")
    assert candidate.source_events[0].observation_id == ObservationId("obs-event-1")
    assert candidate.confidence == approx(0.82)
    assert candidate.reason
    assert candidate.retrieval.topics == ("local-llm", "debugging")


def test_candidate_defaults_to_review_required_policy() -> None:
    """Shared episodic candidate は自動保存せず review-required を既定にする。"""
    candidate = SharedEpisodicMemoryCandidate(
        summary="Iris とユーザーが初めて内輪ネタを作った。",
        kind=SharedEpisodicMemoryKind.RUNNING_JOKE,
        actor_id=ActorId("actor-1"),
        account_id=AccountId("account-1"),
        space_id=SpaceId("space-1"),
        source_events=(_source_event(),),
        occurred_at=_LATER,
        confidence=0.75,
        reason="ユーザーが後続ターンで同じ冗談を再利用したため。",
    )

    assert candidate.review_required is True
    assert candidate.admission_policy is SharedEpisodicAdmissionPolicy.REVIEW_REQUIRED
    assert candidate.admission_risk is SharedEpisodicAdmissionRisk.NORMAL


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_candidate_rejects_invalid_confidence(confidence: float) -> None:
    """Confidence は policy 判断に使うため 0..1 に制限する。"""
    with pytest.raises(ValidationError):
        SharedEpisodicMemoryCandidate(
            summary="共有イベント。",
            kind=SharedEpisodicMemoryKind.SHARED_EVENT,
            actor_id=ActorId("actor-1"),
            account_id=AccountId("account-1"),
            space_id=SpaceId("space-1"),
            source_events=(_source_event(),),
            occurred_at=_LATER,
            confidence=confidence,
            reason="test",
        )


def test_candidate_requires_source_events() -> None:
    """共有体験候補は根拠 source event を必ず保持する。"""
    with pytest.raises(ValidationError):
        _candidate(source_events=())


def test_candidate_rejects_blank_summary() -> None:
    """Summary は review 監査可能な説明を必須にする。"""
    with pytest.raises(ValidationError):
        SharedEpisodicMemoryCandidate(
            summary="   ",
            kind=SharedEpisodicMemoryKind.SHARED_EVENT,
            actor_id=ActorId("actor-1"),
            account_id=AccountId("account-1"),
            space_id=SpaceId("space-1"),
            source_events=(_source_event(),),
            occurred_at=_LATER,
            confidence=0.8,
            reason="test",
        )


def test_candidate_rejects_blank_reason() -> None:
    """Reason は review 監査可能な根拠を必須にする。"""
    with pytest.raises(ValidationError):
        SharedEpisodicMemoryCandidate(
            summary="共有イベント。",
            kind=SharedEpisodicMemoryKind.SHARED_EVENT,
            actor_id=ActorId("actor-1"),
            account_id=AccountId("account-1"),
            space_id=SpaceId("space-1"),
            source_events=(_source_event(),),
            occurred_at=_LATER,
            confidence=0.8,
            reason="   ",
        )


def test_candidate_rejects_blank_actor_id() -> None:
    """Actor boundary は空 ID で失われてはならない。"""
    with pytest.raises(ValidationError):
        SharedEpisodicMemoryCandidate(
            summary="共有イベント。",
            kind=SharedEpisodicMemoryKind.SHARED_EVENT,
            actor_id=ActorId(""),
            account_id=AccountId("account-1"),
            space_id=SpaceId("space-1"),
            source_events=(_source_event(),),
            occurred_at=_LATER,
            confidence=0.8,
            reason="test",
        )


def test_candidate_rejects_blank_account_id() -> None:
    """Account boundary は空 ID で失われてはならない。"""
    with pytest.raises(ValidationError):
        SharedEpisodicMemoryCandidate(
            summary="共有イベント。",
            kind=SharedEpisodicMemoryKind.SHARED_EVENT,
            actor_id=ActorId("actor-1"),
            account_id=AccountId(""),
            space_id=SpaceId("space-1"),
            source_events=(_source_event(),),
            occurred_at=_LATER,
            confidence=0.8,
            reason="test",
        )


def test_candidate_rejects_blank_space_id() -> None:
    """Space boundary は空 ID で失われてはならない。"""
    with pytest.raises(ValidationError):
        SharedEpisodicMemoryCandidate(
            summary="共有イベント。",
            kind=SharedEpisodicMemoryKind.SHARED_EVENT,
            actor_id=ActorId("actor-1"),
            account_id=AccountId("account-1"),
            space_id=SpaceId(""),
            source_events=(_source_event(),),
            occurred_at=_LATER,
            confidence=0.8,
            reason="test",
        )


def test_source_event_rejects_blank_source_event_id() -> None:
    """Source event ID は空白だけにできない。"""
    with pytest.raises(ValidationError):
        SharedEpisodicSourceEventRef(
            source_event_id=" ",
            observation_id=ObservationId("obs-1"),
            occurred_at=_NOW,
        )


def test_private_sensitive_and_embarrassing_candidates_remain_review_required() -> None:
    """機微・羞恥を含む共有記憶は無条件保存されない。"""
    for risk in (
        SharedEpisodicAdmissionRisk.PRIVATE,
        SharedEpisodicAdmissionRisk.SENSITIVE,
        SharedEpisodicAdmissionRisk.EMBARRASSING,
    ):
        candidate = _candidate(admission_risk=risk)

        assert candidate.review_required is True
        assert candidate.admission_policy is SharedEpisodicAdmissionPolicy.REVIEW_REQUIRED


def test_secret_like_candidate_must_be_rejected() -> None:
    """Secret-like な共有エピソードは pending review に入れず reject 扱いにする。"""
    with pytest.raises(ValidationError):
        _candidate(admission_risk=SharedEpisodicAdmissionRisk.SECRET_LIKE)

    rejected = _candidate(
        admission_risk=SharedEpisodicAdmissionRisk.SECRET_LIKE,
        admission_policy=SharedEpisodicAdmissionPolicy.REJECT,
        review_required=False,
    )

    assert rejected.admission_policy is SharedEpisodicAdmissionPolicy.REJECT
    assert rejected.review_required is False


def test_review_required_policy_cannot_disable_review_flag() -> None:
    """review-required policy で review_required=False は許可しない。"""
    with pytest.raises(ValidationError):
        _candidate(review_required=False)


def test_reject_policy_cannot_keep_review_required_flag() -> None:
    """Reject policy は pending review に入らない候補として表現する。"""
    with pytest.raises(ValidationError):
        _candidate(admission_policy=SharedEpisodicAdmissionPolicy.REJECT)


def test_retrieval_metadata_rejects_blank_topics() -> None:
    """Retrieval metadata は空 topic を downstream に渡さない。"""
    with pytest.raises(ValidationError):
        SharedEpisodicRetrievalMetadata(topics=("local-llm", " "))
