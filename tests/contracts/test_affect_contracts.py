"""Affect persistence contract tests."""

from __future__ import annotations

from datetime import UTC, datetime
import json

import pytest

from iris.contracts.affect import AffectBaselineRecord, AffectScope
from iris.core.ids import ActorId, ObservationId
from tests.helpers.immutability import assert_frozen_field


def _unknown_affect_scope() -> AffectScope:
    scope: AffectScope = json.loads('"invalid"')
    return scope


def test_affect_baseline_record_is_immutable() -> None:
    """AffectBaselineRecord is frozen."""
    record = AffectBaselineRecord(scope=AffectScope.GLOBAL, valence=0.1)

    assert_frozen_field(record, "valence", 0.2)


def test_global_affect_must_not_have_actor_id() -> None:
    """Global affect baseline rejects actor_id."""
    with pytest.raises(ValueError, match="global"):
        AffectBaselineRecord(scope=AffectScope.GLOBAL, actor_id=ActorId("actor-1"))


def test_actor_affect_requires_actor_id() -> None:
    """Actor-scoped affect baseline requires actor_id."""
    with pytest.raises(ValueError, match="actor"):
        AffectBaselineRecord(scope=AffectScope.ACTOR)


def test_affect_baseline_rejects_unknown_scope() -> None:
    """AffectBaselineRecord rejects unknown runtime scope values."""
    with pytest.raises(ValueError, match="unknown affect scope"):
        AffectBaselineRecord(scope=_unknown_affect_scope())


def test_affect_baseline_validates_vad_ranges() -> None:
    """AffectBaselineRecord validates VAD ranges."""
    with pytest.raises(ValueError, match="valence"):
        AffectBaselineRecord(scope=AffectScope.GLOBAL, valence=1.1)
    with pytest.raises(ValueError, match="arousal"):
        AffectBaselineRecord(scope=AffectScope.GLOBAL, arousal=-1.1)
    with pytest.raises(ValueError, match="dominance"):
        AffectBaselineRecord(scope=AffectScope.GLOBAL, dominance=1.1)


def test_affect_baseline_preserves_contract_fields() -> None:
    """AffectBaselineRecord preserves scope, values, and provenance."""
    created_at = datetime(2026, 6, 24, tzinfo=UTC)
    record = AffectBaselineRecord(
        scope=AffectScope.ACTOR,
        actor_id=ActorId("actor-1"),
        mood_label="positive",
        valence=0.4,
        arousal=0.2,
        dominance=0.1,
        affect_summary="positive VAD",
        source_observation_id=ObservationId("obs-1"),
        created_at=created_at,
        updated_at=created_at,
    )

    assert record.scope == AffectScope.ACTOR
    assert record.actor_id == ActorId("actor-1")
    assert record.source_observation_id == ObservationId("obs-1")
    assert record.version == 1
