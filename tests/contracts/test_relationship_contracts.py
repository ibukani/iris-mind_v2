"""Relationship persistence contract tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.contracts.relationship import RelationshipSnapshotRecord
from iris.core.ids import ActorId, ObservationId
from tests.helpers.immutability import assert_frozen_field


def test_relationship_record_is_immutable() -> None:
    """RelationshipSnapshotRecord is frozen."""
    record = RelationshipSnapshotRecord(actor_id=ActorId("actor-1"))

    assert_frozen_field(record, "affinity", 0.5)


def test_relationship_record_requires_actor_id() -> None:
    """RelationshipSnapshotRecord rejects missing actor_id."""
    with pytest.raises(ValueError, match="actor_id"):
        RelationshipSnapshotRecord(actor_id=ActorId(""))


def test_relationship_record_validates_value_ranges() -> None:
    """RelationshipSnapshotRecord validates affinity/trust/familiarity ranges."""
    with pytest.raises(ValueError, match="affinity"):
        RelationshipSnapshotRecord(actor_id=ActorId("actor-1"), affinity=1.1)
    with pytest.raises(ValueError, match="trust"):
        RelationshipSnapshotRecord(actor_id=ActorId("actor-1"), trust=-0.1)
    with pytest.raises(ValueError, match="familiarity"):
        RelationshipSnapshotRecord(actor_id=ActorId("actor-1"), familiarity=1.1)


def test_relationship_record_accepts_contract_fields() -> None:
    """RelationshipSnapshotRecord preserves typed ownership and provenance fields."""
    created_at = datetime(2026, 6, 24, tzinfo=UTC)
    record = RelationshipSnapshotRecord(
        actor_id=ActorId("actor-1"),
        actor_label="Mina",
        affinity=0.2,
        trust=0.6,
        familiarity=0.3,
        relationship_summary="Mina: neutral relationship",
        source_observation_id=ObservationId("obs-1"),
        created_at=created_at,
        updated_at=created_at,
    )

    assert record.actor_id == ActorId("actor-1")
    assert record.source_observation_id == ObservationId("obs-1")
    assert record.created_at == created_at
    assert record.version == 1
