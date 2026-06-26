"""SQLiteAffectStore tests."""

from __future__ import annotations

import time
from pathlib import Path

from iris.adapters.affect.sqlite import SQLiteAffectStore
from iris.contracts.affect import AffectBaselineRecord
from iris.core.ids import ActorId, ObservationId


def test_sqlite_affect_store_upserts_and_gets_global(tmp_path: Path) -> None:
    """Upsert then get returns the global affect baseline."""
    store = SQLiteAffectStore(tmp_path / "state.db")
    record = AffectBaselineRecord(
        scope="global",
        mood_label="positive",
        valence=0.5,
        source_observation_id=ObservationId("obs-1"),
    )

    stored = store.upsert_global(record)
    loaded = store.get_global()

    assert loaded == stored
    assert loaded is not None
    assert loaded.created_at is not None
    assert loaded.updated_at is not None


def test_sqlite_affect_update_preserves_created_at_and_advances_updated_at(
    tmp_path: Path,
) -> None:
    """Update preserves created_at and advances updated_at for global baseline."""
    store = SQLiteAffectStore(tmp_path / "state.db")
    first = store.upsert_global(AffectBaselineRecord(scope="global", valence=0.1))
    time.sleep(0.001)
    second = store.upsert_global(AffectBaselineRecord(scope="global", valence=0.4))

    assert second.created_at == first.created_at
    assert second.updated_at is not None
    assert first.updated_at is not None
    assert second.updated_at > first.updated_at
    assert second.valence == 0.4


def test_sqlite_affect_survives_new_store_instance(tmp_path: Path) -> None:
    """Affect baseline survives a new store instance using the same DB path."""
    db_path = tmp_path / "state.db"
    SQLiteAffectStore(db_path).upsert_global(
        AffectBaselineRecord(scope="global", valence=0.2),
    )

    loaded = SQLiteAffectStore(db_path).get_global()

    assert loaded is not None
    assert loaded.valence == 0.2


def test_sqlite_affect_global_and_actor_are_separate(tmp_path: Path) -> None:
    """Actor-scoped affect does not overwrite global affect."""
    store = SQLiteAffectStore(tmp_path / "state.db")
    store.upsert_global(AffectBaselineRecord(scope="global", valence=0.2))
    store.upsert_for_actor(
        AffectBaselineRecord(
            scope="actor",
            actor_id=ActorId("actor-1"),
            valence=0.7,
        ),
    )

    global_record = store.get_global()
    actor_record = store.get_for_actor(ActorId("actor-1"))

    assert global_record is not None
    assert actor_record is not None
    assert global_record.valence == 0.2
    assert actor_record.valence == 0.7


def test_sqlite_affect_actor_uniqueness(tmp_path: Path) -> None:
    """Actor-scoped affect is unique by actor_id."""
    store = SQLiteAffectStore(tmp_path / "state.db")
    store.upsert_for_actor(
        AffectBaselineRecord(scope="actor", actor_id=ActorId("actor-1"), valence=0.1),
    )
    store.upsert_for_actor(
        AffectBaselineRecord(scope="actor", actor_id=ActorId("actor-1"), valence=0.5),
    )

    loaded = store.get_for_actor(ActorId("actor-1"))

    assert loaded is not None
    assert loaded.valence == 0.5
