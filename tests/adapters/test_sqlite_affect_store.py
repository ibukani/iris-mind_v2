"""SQLiteAffectStore tests."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from iris.adapters.sqlite.affect_store import SQLiteAffectStore
from iris.contracts.affect import AffectBaselineRecord, AffectScope
from iris.core.ids import ActorId, ObservationId
from tests.helpers.approx import approx

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path


@pytest.fixture
async def store(tmp_path: Path) -> AsyncGenerator[SQLiteAffectStore]:
    """Fixture for SQLiteAffectStore.

    Yields:
        The store.
    """
    store = SQLiteAffectStore(tmp_path / "state.db")
    yield store
    await store.close()


@pytest.mark.anyio
async def test_sqlite_affect_store_upserts_and_gets_global(store: SQLiteAffectStore) -> None:
    """Upsert then get returns the global affect baseline."""
    record = AffectBaselineRecord(
        scope=AffectScope.GLOBAL,
        mood_label="positive",
        valence=0.5,
        source_observation_id=ObservationId("obs-1"),
    )

    stored = await store.upsert_global(record)
    loaded = await store.get_global()

    assert loaded == stored
    assert loaded is not None
    assert loaded.created_at is not None
    assert loaded.updated_at is not None


@pytest.mark.anyio
async def test_sqlite_affect_store_creates_parent_directory(tmp_path: Path) -> None:
    """Nested DB path parent directory is created during initialization."""
    store = SQLiteAffectStore(tmp_path / "nested" / "state.db")
    record = AffectBaselineRecord(
        scope=AffectScope.GLOBAL,
        mood_label="positive",
        valence=0.5,
        source_observation_id=ObservationId("obs-nested"),
    )

    stored = await store.upsert_global(record)
    loaded = await store.get_global()

    assert loaded == stored
    assert (tmp_path / "nested" / "state.db").exists()
    await store.close()


@pytest.mark.anyio
async def test_sqlite_affect_update_preserves_created_at_and_advances_updated_at(
    store: SQLiteAffectStore,
) -> None:
    """Update preserves created_at and advances updated_at for global baseline."""
    first = await store.upsert_global(AffectBaselineRecord(scope=AffectScope.GLOBAL, valence=0.1))
    await asyncio.sleep(0.001)
    second = await store.upsert_global(AffectBaselineRecord(scope=AffectScope.GLOBAL, valence=0.4))

    assert second.created_at == first.created_at
    assert second.updated_at is not None
    assert first.updated_at is not None
    assert second.updated_at > first.updated_at
    assert second.valence == approx(0.4)


@pytest.mark.anyio
async def test_sqlite_affect_survives_new_store_instance(tmp_path: Path) -> None:
    """Affect baseline survives a new store instance using the same DB path."""
    db_path = tmp_path / "state.db"
    store1 = SQLiteAffectStore(db_path)
    await store1.upsert_global(
        AffectBaselineRecord(scope=AffectScope.GLOBAL, valence=0.2),
    )
    await store1.close()

    store2 = SQLiteAffectStore(db_path)
    loaded = await store2.get_global()

    assert loaded is not None
    assert loaded.valence == approx(0.2)
    await store2.close()


@pytest.mark.anyio
async def test_sqlite_affect_global_and_actor_are_separate(store: SQLiteAffectStore) -> None:
    """Actor-scoped affect does not overwrite global affect."""
    await store.upsert_global(AffectBaselineRecord(scope=AffectScope.GLOBAL, valence=0.2))
    await store.upsert_for_actor(
        AffectBaselineRecord(
            scope=AffectScope.ACTOR,
            actor_id=ActorId("actor-1"),
            valence=0.7,
        ),
    )

    global_record = await store.get_global()
    actor_record = await store.get_for_actor(ActorId("actor-1"))

    assert global_record is not None
    assert actor_record is not None
    assert global_record.valence == approx(0.2)
    assert actor_record.valence == approx(0.7)


@pytest.mark.anyio
async def test_sqlite_affect_actor_uniqueness(store: SQLiteAffectStore) -> None:
    """Actor-scoped affect is unique by actor_id."""
    await store.upsert_for_actor(
        AffectBaselineRecord(scope=AffectScope.ACTOR, actor_id=ActorId("actor-1"), valence=0.1),
    )
    await store.upsert_for_actor(
        AffectBaselineRecord(scope=AffectScope.ACTOR, actor_id=ActorId("actor-1"), valence=0.5),
    )

    loaded = await store.get_for_actor(ActorId("actor-1"))

    assert loaded is not None
    assert loaded.valence == approx(0.5)
