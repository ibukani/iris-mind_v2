"""SQLiteRelationshipStore tests."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from iris.adapters.persistence.sqlite.stores.relationship import SQLiteRelationshipStore
from iris.contracts.relationship import RelationshipSnapshotRecord
from iris.core.ids import ActorId, ObservationId
from tests.helpers.approx import approx

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path


@pytest.fixture
async def store(tmp_path: Path) -> AsyncGenerator[SQLiteRelationshipStore]:
    """Fixture for SQLiteRelationshipStore.

    Yields:
        The store.
    """
    store = SQLiteRelationshipStore(tmp_path / "state.db")
    yield store
    await store.close()


@pytest.mark.anyio
async def test_sqlite_relationship_store_upserts_and_gets(store: SQLiteRelationshipStore) -> None:
    """Upsert then get returns the stored relationship record."""
    record = RelationshipSnapshotRecord(
        actor_id=ActorId("actor-1"),
        actor_label="Mina",
        affinity=0.2,
        trust=0.6,
        familiarity=0.3,
        source_observation_id=ObservationId("obs-1"),
    )

    stored = await store.upsert(record)
    loaded = await store.get(ActorId("actor-1"))

    assert loaded == stored
    assert loaded is not None
    assert loaded.created_at is not None
    assert loaded.updated_at is not None


@pytest.mark.anyio
async def test_sqlite_relationship_store_creates_parent_directory(tmp_path: Path) -> None:
    """Nested DB path parent directory is created during initialization."""
    store = SQLiteRelationshipStore(tmp_path / "nested" / "state.db")
    record = RelationshipSnapshotRecord(
        actor_id=ActorId("actor-nested"),
        actor_label="Mina",
        affinity=0.2,
        trust=0.6,
        familiarity=0.3,
        source_observation_id=ObservationId("obs-nested"),
    )

    stored = await store.upsert(record)
    loaded = await store.get(ActorId("actor-nested"))

    assert loaded == stored
    assert (tmp_path / "nested" / "state.db").exists()
    await store.close()


@pytest.mark.anyio
async def test_sqlite_relationship_update_preserves_created_at_and_advances_updated_at(
    store: SQLiteRelationshipStore,
) -> None:
    """Update preserves created_at and advances updated_at for the same actor."""
    first = await store.upsert(RelationshipSnapshotRecord(actor_id=ActorId("actor-1")))
    await asyncio.sleep(0.001)
    second = await store.upsert(
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
    assert second.affinity == approx(0.4)


@pytest.mark.anyio
async def test_sqlite_relationship_survives_new_store_instance(tmp_path: Path) -> None:
    """Relationship state survives a new store instance using the same DB path."""
    db_path = tmp_path / "state.db"
    store1 = SQLiteRelationshipStore(db_path)
    await store1.upsert(
        RelationshipSnapshotRecord(actor_id=ActorId("actor-1"), familiarity=0.5),
    )
    await store1.close()

    store2 = SQLiteRelationshipStore(db_path)
    loaded = await store2.get(ActorId("actor-1"))

    assert loaded is not None
    assert loaded.familiarity == approx(0.5)
    await store2.close()


@pytest.mark.anyio
async def test_sqlite_relationship_actor_uniqueness(store: SQLiteRelationshipStore) -> None:
    """Relationship state is unique by actor_id."""
    await store.upsert(RelationshipSnapshotRecord(actor_id=ActorId("actor-1"), affinity=0.1))
    await store.upsert(RelationshipSnapshotRecord(actor_id=ActorId("actor-1"), affinity=0.3))

    loaded = await store.get(ActorId("actor-1"))

    assert loaded is not None
    assert loaded.affinity == approx(0.3)
