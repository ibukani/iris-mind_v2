"""Typed appraisal signal から relationship update candidate を計算する policy。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.cognitive.affect.common import clamp_value
from iris.contracts.appraisal import (
    APPRAISAL_RELATIONSHIP_CANDIDATE_SIGNAL_KINDS,
    AppraisalSignal,
    AppraisalSignalKind,
)
from iris.contracts.relationship_update import (
    RELATIONSHIP_UPDATE_POLICY_DEFAULTS,
    RelationshipDeltaBounds,
    RelationshipStateDelta,
    RelationshipUpdateCandidate,
    RelationshipUpdateDecisionKind,
    RelationshipUpdatePolicyConfig,
    RelationshipUpdatePolicyResult,
    RelationshipUpdateReasonKind,
    RelationshipUpdateSourceRef,
)

if TYPE_CHECKING:
    from iris.contracts.companion_affect import CompanionInteractionScope
    from iris.core.ids import ObservationId

_POSITIVE_TRUST_RATIO = 1.0 / 3.0
_NEGATIVE_TRUST_RATIO = 1.0 / 3.0


def compute_relationship_update_policy(
    signals: tuple[AppraisalSignal, ...],
    *,
    interaction_scope: CompanionInteractionScope,
    source_event_ids: tuple[str, ...] = (),
    decay_multiplier: float = 1.0,
    config: RelationshipUpdatePolicyConfig = RELATIONSHIP_UPDATE_POLICY_DEFAULTS,
) -> RelationshipUpdatePolicyResult:
    """Typed appraisal signal から bounded relationship update decision を返す。

    Raw VAD / sentiment score は入力に取らない。`attitude_toward_iris` だけが
    automatic bounded candidate の source になり、他 signal は zero-delta decision にする。

    Returns:
        RelationshipUpdatePolicyResult: #72 worker が参照できる policy decision。
    """
    bounded_decay = clamp_value(decay_multiplier, lower=0.0, upper=1.0)
    bounds = config.bounds_for_scope(interaction_scope)
    candidates = tuple(
        _candidate_for_signal(
            signal,
            bounds=bounds,
            source_event_ids=source_event_ids,
            decay_multiplier=bounded_decay,
            config=config,
        )
        for signal in signals
    )
    return RelationshipUpdatePolicyResult(
        interaction_scope=interaction_scope,
        candidates=candidates,
    )


def _candidate_for_signal(
    signal: AppraisalSignal,
    *,
    bounds: RelationshipDeltaBounds,
    source_event_ids: tuple[str, ...],
    decay_multiplier: float,
    config: RelationshipUpdatePolicyConfig,
) -> RelationshipUpdateCandidate:
    source_ref = _source_ref(signal, source_event_ids)
    if signal.kind not in APPRAISAL_RELATIONSHIP_CANDIDATE_SIGNAL_KINDS:
        return _suppressed_candidate(signal, bounds=bounds, source_ref=source_ref)

    proposed_delta = _bounded_attitude_delta(
        signal,
        bounds=bounds,
        decay_multiplier=decay_multiplier,
    )
    reason_kind = _attitude_reason_kind(signal, proposed_delta, config)
    decision_kind = _attitude_decision_kind(signal, proposed_delta, config)
    return RelationshipUpdateCandidate(
        decision_kind=decision_kind,
        delta=proposed_delta,
        bounds=bounds,
        reason_kind=reason_kind,
        reason=_candidate_reason(signal, decision_kind, reason_kind),
        confidence=signal.confidence,
        source_refs=(source_ref,),
        source_observation_ids=_source_observation_ids(source_ref),
        source_event_ids=_source_event_ids(source_ref),
        review_required=decision_kind is RelationshipUpdateDecisionKind.REVIEW_REQUIRED,
    )


def _bounded_attitude_delta(
    signal: AppraisalSignal,
    *,
    bounds: RelationshipDeltaBounds,
    decay_multiplier: float,
) -> RelationshipStateDelta:
    polarity = clamp_value(signal.polarity)
    confidence_weight = signal.confidence
    affinity = polarity * bounds.max_abs_affinity_delta * confidence_weight * decay_multiplier
    trust_ratio = _POSITIVE_TRUST_RATIO if polarity >= 0.0 else _NEGATIVE_TRUST_RATIO
    trust = (
        polarity * bounds.max_abs_trust_delta * trust_ratio * confidence_weight * decay_multiplier
    )
    return RelationshipStateDelta(
        affinity=_cap_abs(affinity, bounds.max_abs_affinity_delta),
        trust=_cap_abs(trust, bounds.max_abs_trust_delta),
    )


def _attitude_decision_kind(
    signal: AppraisalSignal,
    delta: RelationshipStateDelta,
    config: RelationshipUpdatePolicyConfig,
) -> RelationshipUpdateDecisionKind:
    if delta.is_zero:
        return RelationshipUpdateDecisionKind.SUPPRESSED
    if signal.confidence < config.min_automatic_confidence:
        return RelationshipUpdateDecisionKind.REVIEW_REQUIRED
    if delta.max_abs_component >= config.high_magnitude_review_threshold:
        return RelationshipUpdateDecisionKind.REVIEW_REQUIRED
    return RelationshipUpdateDecisionKind.AUTOMATIC_BOUNDED


def _attitude_reason_kind(
    signal: AppraisalSignal,
    delta: RelationshipStateDelta,
    config: RelationshipUpdatePolicyConfig,
) -> RelationshipUpdateReasonKind:
    reason_kind = RelationshipUpdateReasonKind.NEGATIVE_ATTITUDE_TOWARD_IRIS
    if delta.is_zero:
        reason_kind = RelationshipUpdateReasonKind.ZERO_DELTA_ATTITUDE
    elif signal.confidence < config.min_automatic_confidence:
        reason_kind = RelationshipUpdateReasonKind.LOW_CONFIDENCE_ATTITUDE
    elif delta.max_abs_component >= config.high_magnitude_review_threshold:
        reason_kind = RelationshipUpdateReasonKind.HIGH_MAGNITUDE_ATTITUDE
    elif signal.polarity >= 0.0:
        reason_kind = RelationshipUpdateReasonKind.POSITIVE_ATTITUDE_TOWARD_IRIS
    return reason_kind


def _suppressed_candidate(
    signal: AppraisalSignal,
    *,
    bounds: RelationshipDeltaBounds,
    source_ref: RelationshipUpdateSourceRef,
) -> RelationshipUpdateCandidate:
    reason_kind = _suppressed_reason_kind(signal)
    return RelationshipUpdateCandidate(
        decision_kind=RelationshipUpdateDecisionKind.SUPPRESSED,
        delta=RelationshipStateDelta(),
        bounds=bounds,
        reason_kind=reason_kind,
        reason=_candidate_reason(signal, RelationshipUpdateDecisionKind.SUPPRESSED, reason_kind),
        confidence=signal.confidence,
        source_refs=(source_ref,),
        source_observation_ids=_source_observation_ids(source_ref),
        source_event_ids=_source_event_ids(source_ref),
    )


def _suppressed_reason_kind(signal: AppraisalSignal) -> RelationshipUpdateReasonKind:
    if signal.kind is AppraisalSignalKind.DEPENDENCY_RISK_HINT:
        return RelationshipUpdateReasonKind.DEPENDENCY_RISK_BOUNDARY
    return RelationshipUpdateReasonKind.NON_RELATIONSHIP_SIGNAL


def _candidate_reason(
    signal: AppraisalSignal,
    decision_kind: RelationshipUpdateDecisionKind,
    reason_kind: RelationshipUpdateReasonKind,
) -> str:
    return (
        f"{decision_kind.value}: {reason_kind.value} from "
        f"{signal.kind.value} signal ({signal.reason})"
    )


def _source_ref(
    signal: AppraisalSignal, source_event_ids: tuple[str, ...]
) -> RelationshipUpdateSourceRef:
    return RelationshipUpdateSourceRef(
        signal_kind=signal.kind,
        source_observation_id=signal.source_observation_id,
        source_event_ids=source_event_ids,
        source_reason=signal.reason,
        source_confidence=signal.confidence,
    )


def _source_observation_ids(source_ref: RelationshipUpdateSourceRef) -> tuple[ObservationId, ...]:
    if source_ref.source_observation_id is None:
        return ()
    return (source_ref.source_observation_id,)


def _source_event_ids(source_ref: RelationshipUpdateSourceRef) -> tuple[str, ...]:
    return source_ref.source_event_ids


def _cap_abs(value: float, maximum: float) -> float:
    return clamp_value(value, lower=-maximum, upper=maximum)
