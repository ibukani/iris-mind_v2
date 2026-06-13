"""Runtime wiring helper tests for state stores."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from iris.adapters.accounts.memory import InMemoryAccountStore
from iris.adapters.accounts.sqlite import SQLiteAccountStore
from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.adapters.memory.sqlite import SQLiteMemoryStore
from iris.runtime.activity.journal import InMemoryActivityJournal
from iris.runtime.activity.projections import InMemoryActivityProjectionStore
from iris.runtime.config import default_runtime_config
from iris.runtime.config.state import RuntimeStateConfig
from iris.runtime.presence.store import InMemoryPresenceStore
from iris.runtime.spaces.occupancy_store import InMemorySpaceOccupancyStore
from iris.runtime.wiring.state import wire_runtime_state

if TYPE_CHECKING:
    from pathlib import Path


def test_wire_runtime_state_uses_in_memory_runtime_context_stores_by_default() -> None:
    """デフォルトバックエンドでは runtime context store も in-memory になる。"""
    stores = wire_runtime_state(default_runtime_config())

    assert isinstance(stores.account_store, InMemoryAccountStore)
    assert isinstance(stores.memory_store, InMemoryMemoryStore)
    assert isinstance(stores.activity_journal, InMemoryActivityJournal)
    assert isinstance(stores.activity_projection_store, InMemoryActivityProjectionStore)
    assert isinstance(stores.presence_store, InMemoryPresenceStore)
    assert isinstance(stores.space_occupancy_store, InMemorySpaceOccupancyStore)


def test_wire_runtime_state_keeps_runtime_context_stores_in_memory_for_sqlite(
    tmp_path: Path,
) -> None:
    """SQLite バックエンドでも runtime context store は in-memory のままである。"""
    db_path = tmp_path / "state.db"
    config = default_runtime_config()
    config = replace(
        config,
        state=RuntimeStateConfig(backend="sqlite", sqlite_path=str(db_path)),
    )

    stores = wire_runtime_state(config)

    assert isinstance(stores.account_store, SQLiteAccountStore)
    assert isinstance(stores.memory_store, SQLiteMemoryStore)
    assert isinstance(stores.activity_journal, InMemoryActivityJournal)
    assert isinstance(stores.activity_projection_store, InMemoryActivityProjectionStore)
    assert isinstance(stores.presence_store, InMemoryPresenceStore)
    assert isinstance(stores.space_occupancy_store, InMemorySpaceOccupancyStore)
