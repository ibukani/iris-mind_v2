"""Appraisal semantics contract tests。"""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from iris.contracts.appraisal import (
    APPRAISAL_RELATIONSHIP_CANDIDATE_SIGNAL_KINDS,
    APPRAISAL_WORKER_READABLE_SIGNAL_KINDS,
    AppraisalSafetyHintKind,
    AppraisalSemantics,
    AppraisalSignal,
    AppraisalSignalKind,
    AppraisalSourceSpan,
    appraisal_state_boundary_for_kind,
)
from iris.contracts.companion_affect import CompanionAffectStateKind
from iris.core.ids import ObservationId

EXPECTED_SIGNAL_KINDS = {
    "user_emotion",
    "attitude_toward_iris",
    "topic_sentiment",
    "care_intent",
    "dependency_risk_hint",
}


def _span(text: str = "悲しい") -> AppraisalSourceSpan:
    return AppraisalSourceSpan(start_index=0, end_index=len(text), text=text)


def test_signal_kinds_are_stable_for_downstream_workers() -> None:
    """#102 / #72 / #82 が参照する signal kind 名を固定する。"""
    assert {kind.value for kind in AppraisalSignalKind} == EXPECTED_SIGNAL_KINDS
    assert APPRAISAL_RELATIONSHIP_CANDIDATE_SIGNAL_KINDS == (
        AppraisalSignalKind.ATTITUDE_TOWARD_IRIS,
    )
    assert tuple(AppraisalSignalKind) == APPRAISAL_WORKER_READABLE_SIGNAL_KINDS


def test_signal_has_required_semantic_metadata() -> None:
    """Signal は kind / confidence / reason / source span / provenance を持つ。"""
    signal = AppraisalSignal(
        kind=AppraisalSignalKind.USER_EMOTION,
        label="sad",
        polarity=-0.8,
        confidence=0.9,
        reason="deterministic test",
        source_span=_span(),
        state_boundary=CompanionAffectStateKind.ACTOR_AFFECT_TRACE,
        source_observation_id=ObservationId("obs-appraisal-contract"),
    )

    assert signal.kind is AppraisalSignalKind.USER_EMOTION
    assert abs(signal.confidence - 0.9) <= 1e-12
    assert signal.reason == "deterministic test"
    assert signal.source_span.text == "悲しい"
    assert signal.source_observation_id == ObservationId("obs-appraisal-contract")
    assert signal.metadata == {}


def test_signal_state_boundaries_align_with_companion_affect_model() -> None:
    """#104 の state vocabulary と appraisal signal の対応を固定する。"""
    assert appraisal_state_boundary_for_kind(AppraisalSignalKind.USER_EMOTION) is (
        CompanionAffectStateKind.ACTOR_AFFECT_TRACE
    )
    assert appraisal_state_boundary_for_kind(AppraisalSignalKind.ATTITUDE_TOWARD_IRIS) is (
        CompanionAffectStateKind.ACTOR_RELATIONSHIP
    )
    assert appraisal_state_boundary_for_kind(AppraisalSignalKind.TOPIC_SENTIMENT) is (
        CompanionAffectStateKind.RECENT_INTERACTION_TONE
    )
    assert appraisal_state_boundary_for_kind(AppraisalSignalKind.CARE_INTENT) is (
        CompanionAffectStateKind.RECENT_INTERACTION_TONE
    )
    assert appraisal_state_boundary_for_kind(AppraisalSignalKind.DEPENDENCY_RISK_HINT) is None


def test_dependency_risk_signal_carries_optional_safety_hint() -> None:
    """#82 が後続で拾える safety hint を dependency-risk signal にだけ許す。"""
    signal = AppraisalSignal(
        kind=AppraisalSignalKind.DEPENDENCY_RISK_HINT,
        label="dependency_risk",
        polarity=-1.0,
        confidence=0.85,
        reason="deterministic test",
        source_span=_span("生きていけない"),
        state_boundary=None,
        safety_hint=AppraisalSafetyHintKind.DEPENDENCY_RISK,
    )

    assert signal.safety_hint is AppraisalSafetyHintKind.DEPENDENCY_RISK


def test_non_dependency_signal_rejects_safety_hint() -> None:
    """Safety hint を通常の emotion / relationship signal と混ぜない。"""
    with pytest.raises(ValidationError, match="only dependency_risk_hint"):
        AppraisalSignal(
            kind=AppraisalSignalKind.USER_EMOTION,
            label="sad",
            polarity=-1.0,
            confidence=0.9,
            reason="deterministic test",
            source_span=_span(),
            state_boundary=CompanionAffectStateKind.ACTOR_AFFECT_TRACE,
            safety_hint=AppraisalSafetyHintKind.DEPENDENCY_RISK,
        )


def test_signal_rejects_mismatched_state_boundary() -> None:
    """Signal kind と state boundary の取り違えを拒否する。"""
    with pytest.raises(ValidationError, match="requires state_boundary"):
        AppraisalSignal(
            kind=AppraisalSignalKind.USER_EMOTION,
            label="sad",
            polarity=-1.0,
            confidence=0.9,
            reason="deterministic test",
            source_span=_span(),
            state_boundary=CompanionAffectStateKind.ACTOR_RELATIONSHIP,
        )


def test_signal_validates_confidence_and_span_range() -> None:
    """Confidence と source span は boundary で検証される。"""
    with pytest.raises(ValidationError):
        AppraisalSignal(
            kind=AppraisalSignalKind.USER_EMOTION,
            label="sad",
            polarity=-1.0,
            confidence=1.1,
            reason="deterministic test",
            source_span=_span(),
            state_boundary=CompanionAffectStateKind.ACTOR_AFFECT_TRACE,
        )
    with pytest.raises(ValidationError, match="end_index"):
        AppraisalSourceSpan(start_index=2, end_index=2, text="悲しい")


def test_appraisal_semantics_filters_by_kind() -> None:
    """WorkspaceFrame / worker が kind 別に typed signal を参照できる。"""
    emotion = AppraisalSignal(
        kind=AppraisalSignalKind.USER_EMOTION,
        label="sad",
        polarity=-1.0,
        confidence=0.9,
        reason="deterministic test",
        source_span=_span(),
        state_boundary=CompanionAffectStateKind.ACTOR_AFFECT_TRACE,
    )
    attitude = AppraisalSignal(
        kind=AppraisalSignalKind.ATTITUDE_TOWARD_IRIS,
        label="positive_attitude",
        polarity=1.0,
        confidence=0.9,
        reason="deterministic test",
        source_span=_span("ありがとう"),
        state_boundary=CompanionAffectStateKind.ACTOR_RELATIONSHIP,
    )
    semantics = AppraisalSemantics(signals=(emotion, attitude))

    assert semantics.signals_by_kind(AppraisalSignalKind.USER_EMOTION) == (emotion,)
    assert semantics.signals_by_kind(AppraisalSignalKind.ATTITUDE_TOWARD_IRIS) == (attitude,)
