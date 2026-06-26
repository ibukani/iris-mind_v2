"""Tests for runtime state wiring."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from iris.adapters.accounts.memory import InMemoryAccountStore
from iris.adapters.accounts.sqlite import SQLiteAccountStore
from iris.adapters.affect.memory import InMemoryAffectStore
from iris.adapters.affect.sqlite import SQLiteAffectStore
from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.adapters.memory.sqlite import SQLiteMemoryStore
from iris.adapters.relationship.memory import InMemoryRelationshipStore
from iris.adapters.relationship.sqlite import SQLiteRelationshipStore
from iris.runtime.config import default_runtime_config
from iris.runtime.config.state import RuntimeStateConfig
from iris.runtime.wiring.state import wire_runtime_state

if TYPE_CHECKING:
    from pathlib import Path


def test_wire_memory_backend() -> None:
    """Default state backend wires account and memory stores only."""
    config = default_runtime_config()
    stores = wire_runtime_state(config)

    assert isinstance(stores.account_store, InMemoryAccountStore)
    assert isinstance(stores.memory_store, InMemoryMemoryStore)
    assert isinstance(stores.relationship_store, InMemoryRelationshipStore)
    assert isinstance(stores.affect_store, InMemoryAffectStore)
    assert not hasattr(stores, "space_binding_store")


def test_wire_sqlite_backend(tmp_path: Path) -> None:
    """SQLite backend persists accounts and memory, not SpaceBinding."""
    db_path = tmp_path / "state.db"
    config = default_runtime_config()
    config = replace(config, state=RuntimeStateConfig(backend="sqlite", sqlite_path=str(db_path)))

    stores = wire_runtime_state(config)

    assert isinstance(stores.account_store, SQLiteAccountStore)
    assert isinstance(stores.memory_store, SQLiteMemoryStore)
    assert isinstance(stores.relationship_store, SQLiteRelationshipStore)
    assert isinstance(stores.affect_store, SQLiteAffectStore)
    assert not hasattr(stores, "space_binding_store")
    assert db_path.exists()


def test_wire_memory_backend_uses_independent_stores() -> None:
    """Each in-memory state wiring call returns independent store instances."""
    config = default_runtime_config()

    stores_a = wire_runtime_state(config)
    stores_b = wire_runtime_state(config)

    assert stores_a.account_store is not stores_b.account_store
    assert stores_a.memory_store is not stores_b.memory_store
    assert stores_a.relationship_store is not stores_b.relationship_store
    assert stores_a.affect_store is not stores_b.affect_store
