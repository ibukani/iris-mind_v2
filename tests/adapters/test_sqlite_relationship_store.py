"""SQLiteRelationshipStore tests."""

from __future__ import annotations

import time
from pathlib import Path

from iris.adapters.relationship.sqlite import SQLiteRelationshipStore
from iris.contracts.relationship import RelationshipSnapshotRecord
from iris.core.ids import ActorId, ObservationId


def test_sqlite_relationship_store_upserts_and_gets(tmp_path: Path) -> None:
    """Upsert then get returns the stored relationship record."""
    store = SQLiteRelationshipStore(tmp_path / "state.db")
    record = RelationshipSnapshotRecord(
        actor_id=ActorId("actor-1"),
        actor_label="Mina",
        affinity=0.2,
        trust=0.6,
        familiarity=0.3,
        source_observation_id=ObservationId("obs-1"),
    )

    stored = store.upsert(record)
    loaded = store.get(ActorId("actor-1"))

    assert loaded == stored
    assert loaded is not None
    assert loaded.created_at is not None
    assert loaded.updated_at is not None


def test_sqlite_relationship_update_preserves_created_at_and_advances_updated_at(
    tmp_path: Path,
) -> None:
    """Update preserves created_at and advances updated_at for the same actor."""
    store = SQLiteRelationshipStore(tmp_path / "state.db")
    first = store.upsert(RelationshipSnapshotRecord(actor_id=ActorId("actor-1")))
    time.sleep(0.001)
    second = store.upsert(
        RelationshipSnapshotRecord(
            actor_id=ActorId("actor-1"),
            affinity=0.4,
            trust=0.7,
            familiarity=0.5,
        ),
    )

    assert second.created_at == first.created_at
    assert second.updated_at is not None
    assert first.updated_at is not None
    assert second.updated_at > first.updated_at
    assert second.affinity == 0.4


def test_sqlite_relationship_survives_new_store_instance(tmp_path: Path) -> None:
    """Relationship state survives a new store instance using the same DB path."""
    db_path = tmp_path / "state.db"
    SQLiteRelationshipStore(db_path).upsert(
        RelationshipSnapshotRecord(actor_id=ActorId("actor-1"), familiarity=0.5),
    )

    loaded = SQLiteRelationshipStore(db_path).get(ActorId("actor-1"))

    assert loaded is not None
    assert loaded.familiarity == 0.5


def test_sqlite_relationship_actor_uniqueness(tmp_path: Path) -> None:
    """Relationship state is unique by actor_id."""
    store = SQLiteRelationshipStore(tmp_path / "state.db")
    store.upsert(RelationshipSnapshotRecord(actor_id=ActorId("actor-1"), affinity=0.1))
    store.upsert(RelationshipSnapshotRecord(actor_id=ActorId("actor-1"), affinity=0.3))

    loaded = store.get(ActorId("actor-1"))

    assert loaded is not None
    assert loaded.affinity == 0.3
