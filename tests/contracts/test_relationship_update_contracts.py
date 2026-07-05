"""Relationship update policy v2 contract tests。"""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from iris.contracts.appraisal import AppraisalSignalKind
from iris.contracts.companion_affect import CompanionAffectStateKind, CompanionInteractionScope
from iris.contracts.relationship_update import (
    RELATIONSHIP_UPDATE_POLICY_DEFAULTS,
    RelationshipDeltaBounds,
    RelationshipStateDelta,
    RelationshipUpdateCandidate,
    RelationshipUpdateDecisionKind,
    RelationshipUpdatePolicyConfig,
    RelationshipUpdatePolicyResult,
    RelationshipUpdateReasonKind,
    RelationshipUpdateSourceKind,
    RelationshipUpdateSourceRef,
)
from iris.core.ids import ObservationId
from tests.helpers.approx import approx
from tests.helpers.immutability import assert_frozen_field


def _source_ref() -> RelationshipUpdateSourceRef:
    return RelationshipUpdateSourceRef(
        signal_kind=AppraisalSignalKind.ATTITUDE_TOWARD_IRIS,
        source_observation_id=ObservationId("obs-relationship-update"),
        source_event_ids=("event-relationship-update",),
        source_reason="deterministic test signal",
        source_confidence=0.9,
    )


def _bounds() -> RelationshipDeltaBounds:
    return RelationshipDeltaBounds(
        max_abs_affinity_delta=0.03,
        max_abs_trust_delta=0.01,
    )


def test_policy_defaults_are_stable_before_runtime_config_v2() -> None:
    """#102 の初期 constants は Runtime Config v2 まで contract/test で固定する。"""
    defaults = RELATIONSHIP_UPDATE_POLICY_DEFAULTS

    assert defaults.min_automatic_confidence == approx(0.75)
    assert defaults.high_magnitude_review_threshold == approx(0.025)
    assert defaults.direct_message_bounds.max_abs_affinity_delta == approx(0.03)
    assert defaults.direct_message_bounds.max_abs_trust_delta == approx(0.01)
    assert defaults.group_space_bounds.max_abs_affinity_delta == approx(0.015)
    assert defaults.group_space_bounds.max_abs_trust_delta == approx(0.005)
    assert defaults.bounds_for_scope(CompanionInteractionScope.DIRECT_MESSAGE) == (
        defaults.direct_message_bounds
    )
    assert defaults.bounds_for_scope(CompanionInteractionScope.GROUP_SPACE) == (
        defaults.group_space_bounds
    )


def test_policy_config_rejects_unreachable_high_magnitude_threshold() -> None:
    """High-magnitude threshold は全 cap より大きくして無効化しない。"""
    with pytest.raises(ValidationError, match="high_magnitude_review_threshold"):
        RelationshipUpdatePolicyConfig(high_magnitude_review_threshold=0.05)


def test_policy_config_rejects_group_space_bounds_larger_than_dm() -> None:
    """Group-space cap は DM cap 以下に固定し、誤帰属リスクを増やさない。"""
    with pytest.raises(ValidationError, match="group_space_bounds"):
        RelationshipUpdatePolicyConfig(
            direct_message_bounds=RelationshipDeltaBounds(
                max_abs_affinity_delta=0.03,
                max_abs_trust_delta=0.01,
            ),
            group_space_bounds=RelationshipDeltaBounds(
                max_abs_affinity_delta=0.04,
                max_abs_trust_delta=0.01,
            ),
        )


def test_source_ref_keeps_typed_signal_provenance() -> None:
    """Source ref は typed appraisal signal の provenance を保持する。"""
    source_ref = _source_ref()

    assert source_ref.source_kind is RelationshipUpdateSourceKind.APPRAISAL_SIGNAL
    assert source_ref.signal_kind is AppraisalSignalKind.ATTITUDE_TOWARD_IRIS
    assert source_ref.source_observation_id == ObservationId("obs-relationship-update")
    assert source_ref.source_event_ids == ("event-relationship-update",)
    assert source_ref.source_reason == "deterministic test signal"
    assert source_ref.source_confidence == approx(0.9)


def test_source_ref_rejects_blank_source_event_id() -> None:
    """Source event ID は空白だけにできない。"""
    with pytest.raises(ValidationError, match="source_event_ids"):
        RelationshipUpdateSourceRef(
            signal_kind=AppraisalSignalKind.ATTITUDE_TOWARD_IRIS,
            source_event_ids=(" ",),
            source_reason="deterministic test signal",
            source_confidence=0.9,
        )


def test_candidate_preserves_reason_confidence_source_ids_and_bounds() -> None:
    """Candidate は reason / confidence / source event IDs / bounds を保持する。"""
    source_ref = _source_ref()
    candidate = RelationshipUpdateCandidate(
        decision_kind=RelationshipUpdateDecisionKind.AUTOMATIC_BOUNDED,
        delta=RelationshipStateDelta(affinity=0.02, trust=0.005),
        bounds=_bounds(),
        reason_kind=RelationshipUpdateReasonKind.POSITIVE_ATTITUDE_TOWARD_IRIS,
        reason="positive Iris-directed attitude",
        confidence=0.9,
        source_refs=(source_ref,),
        source_observation_ids=(ObservationId("obs-relationship-update"),),
        source_event_ids=("event-relationship-update",),
    )

    assert candidate.target_state_kind is CompanionAffectStateKind.ACTOR_RELATIONSHIP
    assert candidate.decision_kind is RelationshipUpdateDecisionKind.AUTOMATIC_BOUNDED
    assert candidate.reason_kind is RelationshipUpdateReasonKind.POSITIVE_ATTITUDE_TOWARD_IRIS
    assert candidate.confidence == approx(0.9)
    assert candidate.source_event_ids == ("event-relationship-update",)
    assert candidate.bounds.max_abs_affinity_delta == approx(0.03)
    assert candidate.metadata == {}


def test_candidate_is_immutable() -> None:
    """RelationshipUpdateCandidate は frozen contract。"""
    source_ref = _source_ref()
    candidate = RelationshipUpdateCandidate(
        decision_kind=RelationshipUpdateDecisionKind.AUTOMATIC_BOUNDED,
        delta=RelationshipStateDelta(affinity=0.02),
        bounds=_bounds(),
        reason_kind=RelationshipUpdateReasonKind.POSITIVE_ATTITUDE_TOWARD_IRIS,
        reason="positive Iris-directed attitude",
        confidence=0.9,
        source_refs=(source_ref,),
        source_observation_ids=(ObservationId("obs-relationship-update"),),
        source_event_ids=("event-relationship-update",),
    )

    assert_frozen_field(candidate, "confidence", 0.1)


def test_candidate_rejects_delta_outside_bounds() -> None:
    """Candidate は cap を超える delta を拒否する。"""
    with pytest.raises(ValidationError, match="affinity delta exceeds bounds"):
        RelationshipUpdateCandidate(
            decision_kind=RelationshipUpdateDecisionKind.AUTOMATIC_BOUNDED,
            delta=RelationshipStateDelta(affinity=0.04),
            bounds=_bounds(),
            reason_kind=RelationshipUpdateReasonKind.POSITIVE_ATTITUDE_TOWARD_IRIS,
            reason="positive Iris-directed attitude",
            confidence=0.9,
            source_refs=(_source_ref(),),
            source_observation_ids=(ObservationId("obs-relationship-update"),),
            source_event_ids=("event-relationship-update",),
        )


def test_review_required_decision_is_separate_from_automatic_bounded() -> None:
    """Review-required candidate は automatic bounded と別 decision になる。"""
    candidate = RelationshipUpdateCandidate(
        decision_kind=RelationshipUpdateDecisionKind.REVIEW_REQUIRED,
        delta=RelationshipStateDelta(affinity=0.02),
        bounds=_bounds(),
        reason_kind=RelationshipUpdateReasonKind.LOW_CONFIDENCE_ATTITUDE,
        reason="low confidence Iris-directed attitude",
        confidence=0.4,
        source_refs=(_source_ref(),),
        source_observation_ids=(ObservationId("obs-relationship-update"),),
        source_event_ids=("event-relationship-update",),
        review_required=True,
    )

    assert candidate.review_required is True
    assert candidate.decision_kind is RelationshipUpdateDecisionKind.REVIEW_REQUIRED


def test_review_required_decision_requires_flag() -> None:
    """review_required decision では明示 flag が必須。"""
    with pytest.raises(ValidationError, match="review_required decision"):
        RelationshipUpdateCandidate(
            decision_kind=RelationshipUpdateDecisionKind.REVIEW_REQUIRED,
            delta=RelationshipStateDelta(affinity=0.02),
            bounds=_bounds(),
            reason_kind=RelationshipUpdateReasonKind.LOW_CONFIDENCE_ATTITUDE,
            reason="low confidence Iris-directed attitude",
            confidence=0.4,
            source_refs=(_source_ref(),),
            source_observation_ids=(ObservationId("obs-relationship-update"),),
            source_event_ids=("event-relationship-update",),
        )


def test_review_required_decision_requires_non_zero_delta() -> None:
    """review-required candidate は durable promotion 前の non-zero update に限定する。"""
    with pytest.raises(ValidationError, match="non-zero delta"):
        RelationshipUpdateCandidate(
            decision_kind=RelationshipUpdateDecisionKind.REVIEW_REQUIRED,
            delta=RelationshipStateDelta(),
            bounds=_bounds(),
            reason_kind=RelationshipUpdateReasonKind.LOW_CONFIDENCE_ATTITUDE,
            reason="low confidence Iris-directed attitude",
            confidence=0.4,
            source_refs=(_source_ref(),),
            source_observation_ids=(ObservationId("obs-relationship-update"),),
            source_event_ids=("event-relationship-update",),
            review_required=True,
        )


def test_suppressed_decision_must_keep_zero_delta() -> None:
    """Suppressed candidate は durable update に使える delta を持てない。"""
    with pytest.raises(ValidationError, match="suppressed updates must use a zero delta"):
        RelationshipUpdateCandidate(
            decision_kind=RelationshipUpdateDecisionKind.SUPPRESSED,
            delta=RelationshipStateDelta(affinity=0.01),
            bounds=_bounds(),
            reason_kind=RelationshipUpdateReasonKind.NON_RELATIONSHIP_SIGNAL,
            reason="not a relationship update source",
            confidence=0.8,
            source_refs=(_source_ref(),),
            source_observation_ids=(ObservationId("obs-relationship-update"),),
            source_event_ids=("event-relationship-update",),
        )


def test_candidate_rejects_mismatched_source_id_indexes() -> None:
    """Flattened source IDs は source_refs 由来と一致させる。"""
    with pytest.raises(ValidationError, match="source_observation_ids"):
        RelationshipUpdateCandidate(
            decision_kind=RelationshipUpdateDecisionKind.AUTOMATIC_BOUNDED,
            delta=RelationshipStateDelta(affinity=0.02),
            bounds=_bounds(),
            reason_kind=RelationshipUpdateReasonKind.POSITIVE_ATTITUDE_TOWARD_IRIS,
            reason="positive Iris-directed attitude",
            confidence=0.9,
            source_refs=(_source_ref(),),
            source_observation_ids=(ObservationId("wrong-observation"),),
            source_event_ids=("event-relationship-update",),
        )


def test_policy_result_filters_decisions_for_worker_boundary() -> None:
    """#72 worker が decision kind ごとに candidate を参照できる。"""
    source_ref = _source_ref()
    automatic = RelationshipUpdateCandidate(
        decision_kind=RelationshipUpdateDecisionKind.AUTOMATIC_BOUNDED,
        delta=RelationshipStateDelta(affinity=0.02),
        bounds=_bounds(),
        reason_kind=RelationshipUpdateReasonKind.POSITIVE_ATTITUDE_TOWARD_IRIS,
        reason="positive Iris-directed attitude",
        confidence=0.9,
        source_refs=(source_ref,),
        source_observation_ids=(ObservationId("obs-relationship-update"),),
        source_event_ids=("event-relationship-update",),
    )
    suppressed = RelationshipUpdateCandidate(
        decision_kind=RelationshipUpdateDecisionKind.SUPPRESSED,
        delta=RelationshipStateDelta(),
        bounds=_bounds(),
        reason_kind=RelationshipUpdateReasonKind.NON_RELATIONSHIP_SIGNAL,
        reason="not a relationship update source",
        confidence=0.8,
        source_refs=(source_ref,),
        source_observation_ids=(ObservationId("obs-relationship-update"),),
        source_event_ids=("event-relationship-update",),
    )
    result = RelationshipUpdatePolicyResult(
        interaction_scope=CompanionInteractionScope.DIRECT_MESSAGE,
        candidates=(automatic, suppressed),
    )

    assert result.automatic_candidates == (automatic,)
    assert result.review_required_candidates == ()
    assert result.suppressed_candidates == (suppressed,)
