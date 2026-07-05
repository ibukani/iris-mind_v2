"""Relationship update policy v2 behavior tests。"""

from __future__ import annotations

from iris.cognitive.affect.relationship_update_policy import compute_relationship_update_policy
from iris.contracts.appraisal import (
    AppraisalSafetyHintKind,
    AppraisalSignal,
    AppraisalSignalKind,
    AppraisalSourceSpan,
)
from iris.contracts.companion_affect import CompanionAffectStateKind, CompanionInteractionScope
from iris.contracts.relationship_update import (
    RelationshipDeltaBounds,
    RelationshipUpdateDecisionKind,
    RelationshipUpdatePolicyConfig,
    RelationshipUpdateReasonKind,
)
from iris.core.ids import ObservationId
from tests.helpers.approx import approx


def _span(text: str = "Iris") -> AppraisalSourceSpan:
    return AppraisalSourceSpan(start_index=0, end_index=len(text), text=text)


def _signal(
    kind: AppraisalSignalKind,
    *,
    polarity: float,
    confidence: float = 0.9,
    reason: str = "deterministic test signal",
) -> AppraisalSignal:
    state_boundary = _state_boundary_for_kind(kind)
    safety_hint = (
        AppraisalSafetyHintKind.DEPENDENCY_RISK
        if kind is AppraisalSignalKind.DEPENDENCY_RISK_HINT
        else None
    )
    return AppraisalSignal(
        kind=kind,
        label=kind.value,
        polarity=polarity,
        confidence=confidence,
        reason=reason,
        source_span=_span(),
        state_boundary=state_boundary,
        safety_hint=safety_hint,
        source_observation_id=ObservationId("obs-relationship-policy"),
    )


def test_positive_iris_attitude_creates_automatic_bounded_dm_candidate() -> None:
    """Iris への好意は DM では bounded automatic candidate になる。"""
    result = compute_relationship_update_policy(
        (_signal(AppraisalSignalKind.ATTITUDE_TOWARD_IRIS, polarity=0.5),),
        interaction_scope=CompanionInteractionScope.DIRECT_MESSAGE,
        source_event_ids=("event-1",),
    )

    candidate = result.automatic_candidates[0]
    assert candidate.decision_kind is RelationshipUpdateDecisionKind.AUTOMATIC_BOUNDED
    assert candidate.reason_kind is RelationshipUpdateReasonKind.POSITIVE_ATTITUDE_TOWARD_IRIS
    assert candidate.delta.affinity > 0.0
    assert candidate.delta.affinity <= candidate.bounds.max_abs_affinity_delta
    assert candidate.delta.trust > 0.0
    assert candidate.source_observation_ids == (ObservationId("obs-relationship-policy"),)
    assert candidate.source_event_ids == ("event-1",)
    assert candidate.confidence == approx(0.9)


def test_negative_iris_attitude_creates_bounded_negative_candidate() -> None:
    """Iris への明示的不満だけが bounded negative relationship candidate になる。"""
    result = compute_relationship_update_policy(
        (_signal(AppraisalSignalKind.ATTITUDE_TOWARD_IRIS, polarity=-0.5),),
        interaction_scope=CompanionInteractionScope.DIRECT_MESSAGE,
    )

    candidate = result.automatic_candidates[0]
    assert candidate.reason_kind is RelationshipUpdateReasonKind.NEGATIVE_ATTITUDE_TOWARD_IRIS
    assert candidate.delta.affinity < 0.0
    assert candidate.delta.trust < 0.0
    assert abs(candidate.delta.affinity) <= candidate.bounds.max_abs_affinity_delta
    assert abs(candidate.delta.trust) <= candidate.bounds.max_abs_trust_delta


def test_user_emotion_does_not_become_relationship_update() -> None:
    """User sadness/anxiety は relationship trust / affinity を下げない。"""
    result = compute_relationship_update_policy(
        (_signal(AppraisalSignalKind.USER_EMOTION, polarity=-1.0),),
        interaction_scope=CompanionInteractionScope.DIRECT_MESSAGE,
    )

    candidate = result.suppressed_candidates[0]
    assert result.automatic_candidates == ()
    assert candidate.reason_kind is RelationshipUpdateReasonKind.NON_RELATIONSHIP_SIGNAL
    assert candidate.delta.is_zero
    assert candidate.source_observation_ids == (ObservationId("obs-relationship-policy"),)


def test_topic_sentiment_and_care_intent_are_not_relationship_sources() -> None:
    """Topic sentiment / care intent は ActorRelationshipState source にしない。"""
    result = compute_relationship_update_policy(
        (
            _signal(AppraisalSignalKind.TOPIC_SENTIMENT, polarity=-1.0),
            _signal(AppraisalSignalKind.CARE_INTENT, polarity=1.0),
        ),
        interaction_scope=CompanionInteractionScope.GROUP_SPACE,
    )

    assert result.automatic_candidates == ()
    assert tuple(candidate.reason_kind for candidate in result.suppressed_candidates) == (
        RelationshipUpdateReasonKind.NON_RELATIONSHIP_SIGNAL,
        RelationshipUpdateReasonKind.NON_RELATIONSHIP_SIGNAL,
    )
    assert all(candidate.delta.is_zero for candidate in result.suppressed_candidates)


def test_dependency_risk_hint_is_suppressed_for_safety_boundary() -> None:
    """Dependency-risk hint を好意や信頼として扱わない。"""
    result = compute_relationship_update_policy(
        (_signal(AppraisalSignalKind.DEPENDENCY_RISK_HINT, polarity=-1.0),),
        interaction_scope=CompanionInteractionScope.DIRECT_MESSAGE,
    )

    candidate = result.suppressed_candidates[0]
    assert result.automatic_candidates == ()
    assert candidate.reason_kind is RelationshipUpdateReasonKind.DEPENDENCY_RISK_BOUNDARY
    assert candidate.delta.is_zero


def test_low_confidence_attitude_requires_review() -> None:
    """Low-confidence attitude は automatic ではなく review-required にする。"""
    result = compute_relationship_update_policy(
        (_signal(AppraisalSignalKind.ATTITUDE_TOWARD_IRIS, polarity=1.0, confidence=0.4),),
        interaction_scope=CompanionInteractionScope.DIRECT_MESSAGE,
    )

    candidate = result.review_required_candidates[0]
    assert result.automatic_candidates == ()
    assert candidate.review_required is True
    assert candidate.reason_kind is RelationshipUpdateReasonKind.LOW_CONFIDENCE_ATTITUDE
    assert candidate.delta.affinity > 0.0


def test_high_magnitude_attitude_requires_review_before_promotion() -> None:
    """High-magnitude update は bounded delta でも review-required にする。"""
    config = RelationshipUpdatePolicyConfig(
        high_magnitude_review_threshold=0.01,
        direct_message_bounds=RelationshipDeltaBounds(
            max_abs_affinity_delta=0.03,
            max_abs_trust_delta=0.01,
        ),
        group_space_bounds=RelationshipDeltaBounds(
            max_abs_affinity_delta=0.015,
            max_abs_trust_delta=0.005,
        ),
    )

    result = compute_relationship_update_policy(
        (_signal(AppraisalSignalKind.ATTITUDE_TOWARD_IRIS, polarity=1.0, confidence=0.95),),
        interaction_scope=CompanionInteractionScope.DIRECT_MESSAGE,
        config=config,
    )

    candidate = result.review_required_candidates[0]
    assert candidate.reason_kind is RelationshipUpdateReasonKind.HIGH_MAGNITUDE_ATTITUDE
    assert candidate.review_required is True
    assert candidate.delta.affinity <= candidate.bounds.max_abs_affinity_delta


def test_group_space_uses_smaller_bounds_than_dm() -> None:
    """Group-space は誤帰属を避けるため DM より小さい cap を使う。"""
    signal = _signal(AppraisalSignalKind.ATTITUDE_TOWARD_IRIS, polarity=0.5)
    dm_result = compute_relationship_update_policy(
        (signal,),
        interaction_scope=CompanionInteractionScope.DIRECT_MESSAGE,
    )
    group_result = compute_relationship_update_policy(
        (signal,),
        interaction_scope=CompanionInteractionScope.GROUP_SPACE,
    )

    dm_candidate = dm_result.automatic_candidates[0]
    group_candidate = group_result.automatic_candidates[0]
    assert (
        group_candidate.bounds.max_abs_affinity_delta < dm_candidate.bounds.max_abs_affinity_delta
    )
    assert group_candidate.delta.affinity < dm_candidate.delta.affinity
    assert group_candidate.delta.trust < dm_candidate.delta.trust


def test_decay_multiplier_reduces_bounded_delta() -> None:
    """Decay は candidate delta の magnitude を保守的に下げる。"""
    signal = _signal(AppraisalSignalKind.ATTITUDE_TOWARD_IRIS, polarity=0.5)
    full_result = compute_relationship_update_policy(
        (signal,),
        interaction_scope=CompanionInteractionScope.DIRECT_MESSAGE,
        decay_multiplier=1.0,
    )
    decayed_result = compute_relationship_update_policy(
        (signal,),
        interaction_scope=CompanionInteractionScope.DIRECT_MESSAGE,
        decay_multiplier=0.5,
    )

    full_candidate = full_result.automatic_candidates[0]
    decayed_candidate = decayed_result.automatic_candidates[0]
    assert decayed_candidate.delta.affinity == approx(full_candidate.delta.affinity * 0.5)
    assert decayed_candidate.delta.trust == approx(full_candidate.delta.trust * 0.5)


def test_neutral_or_fully_decayed_attitude_is_suppressed_zero_delta() -> None:
    """Neutral attitude や full decay は automatic non-zero invariant を破らず suppress する。"""
    neutral_result = compute_relationship_update_policy(
        (_signal(AppraisalSignalKind.ATTITUDE_TOWARD_IRIS, polarity=0.0),),
        interaction_scope=CompanionInteractionScope.DIRECT_MESSAGE,
    )
    decayed_result = compute_relationship_update_policy(
        (_signal(AppraisalSignalKind.ATTITUDE_TOWARD_IRIS, polarity=0.5),),
        interaction_scope=CompanionInteractionScope.DIRECT_MESSAGE,
        decay_multiplier=0.0,
    )

    neutral_candidate = neutral_result.suppressed_candidates[0]
    decayed_candidate = decayed_result.suppressed_candidates[0]
    assert neutral_candidate.reason_kind is RelationshipUpdateReasonKind.ZERO_DELTA_ATTITUDE
    assert neutral_candidate.delta.is_zero
    assert decayed_candidate.reason_kind is RelationshipUpdateReasonKind.ZERO_DELTA_ATTITUDE
    assert decayed_candidate.delta.is_zero


def test_source_event_ids_are_attached_to_each_candidate_as_event_provenance() -> None:
    """Turn-level source event IDs は positional に捨てず各 candidate に保持する。"""
    result = compute_relationship_update_policy(
        (
            _signal(AppraisalSignalKind.ATTITUDE_TOWARD_IRIS, polarity=0.5),
            _signal(AppraisalSignalKind.USER_EMOTION, polarity=-1.0),
        ),
        interaction_scope=CompanionInteractionScope.DIRECT_MESSAGE,
        source_event_ids=("event-1", "event-2"),
    )

    assert all(
        candidate.source_event_ids == ("event-1", "event-2") for candidate in result.candidates
    )


def test_policy_does_not_need_raw_affect_score_input() -> None:
    """Policy API は raw score を受け取らず typed signal だけで decision を作る。"""
    result = compute_relationship_update_policy(
        (),
        interaction_scope=CompanionInteractionScope.DIRECT_MESSAGE,
    )

    assert result.candidates == ()


def _state_boundary_for_kind(
    kind: AppraisalSignalKind,
) -> CompanionAffectStateKind | None:
    if kind is AppraisalSignalKind.USER_EMOTION:
        return CompanionAffectStateKind.ACTOR_AFFECT_TRACE
    if kind is AppraisalSignalKind.ATTITUDE_TOWARD_IRIS:
        return CompanionAffectStateKind.ACTOR_RELATIONSHIP
    if kind in {AppraisalSignalKind.TOPIC_SENTIMENT, AppraisalSignalKind.CARE_INTENT}:
        return CompanionAffectStateKind.RECENT_INTERACTION_TONE
    return None
