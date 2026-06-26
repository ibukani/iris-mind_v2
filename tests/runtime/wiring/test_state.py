"""Runtime wiring helper tests for state stores."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from iris.adapters.accounts.memory import InMemoryAccountStore
from iris.adapters.accounts.sqlite import SQLiteAccountStore
from iris.adapters.activity.sqlite_journal import SQLiteActivityJournal
from iris.adapters.affect.memory import InMemoryAffectStore
from iris.adapters.affect.sqlite import SQLiteAffectStore
from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.adapters.memory.sqlite import SQLiteMemoryStore
from iris.adapters.relationship.memory import InMemoryRelationshipStore
from iris.adapters.relationship.sqlite import SQLiteRelationshipStore
from iris.runtime.config import default_runtime_config
from iris.runtime.config.state import RuntimeStateConfig
from iris.runtime.state.activity_journal import InMemoryActivityJournal
from iris.runtime.state.activity_projection import InMemoryActivityProjectionStore
from iris.runtime.state.presence import InMemoryPresenceStore
from iris.runtime.state.space_occupancy import InMemorySpaceOccupancyStore
from iris.runtime.wiring.state import wire_runtime_state

if TYPE_CHECKING:
    from pathlib import Path


def test_wire_runtime_state_uses_in_memory_runtime_context_stores_by_default() -> None:
    """デフォルトバックエンドでは runtime context store も in-memory になる。"""
    stores = wire_runtime_state(default_runtime_config())

    assert isinstance(stores.account_store, InMemoryAccountStore)
    assert isinstance(stores.memory_store, InMemoryMemoryStore)
    assert isinstance(stores.relationship_store, InMemoryRelationshipStore)
    assert isinstance(stores.affect_store, InMemoryAffectStore)
    assert isinstance(stores.activity_journal, InMemoryActivityJournal)
    assert isinstance(stores.activity_projection_store, InMemoryActivityProjectionStore)
    assert isinstance(stores.presence_store, InMemoryPresenceStore)
    assert isinstance(stores.space_occupancy_store, InMemorySpaceOccupancyStore)


def test_wire_runtime_state_promotes_activity_journal_to_sqlite_under_sqlite(
    tmp_path: Path,
) -> None:
    """SQLite バックエンド選択時、activity journal は durable な SQLite 実装になる。

    永続化policy: ``state.backend = "sqlite"`` 選択時、account、memory、activity
    journalがSQLiteへ永続化される。Activity projection、presence、space occupancyは
    process-localのin-memory実装のままとなる。
    """
    db_path = tmp_path / "state.db"
    config = default_runtime_config()
    config = replace(
        config,
        state=RuntimeStateConfig(backend="sqlite", sqlite_path=str(db_path)),
    )

    stores = wire_runtime_state(config)

    assert isinstance(stores.account_store, SQLiteAccountStore)
    assert isinstance(stores.memory_store, SQLiteMemoryStore)
    assert isinstance(stores.relationship_store, SQLiteRelationshipStore)
    assert isinstance(stores.affect_store, SQLiteAffectStore)
    assert isinstance(stores.activity_journal, SQLiteActivityJournal)
    # projection、presence、space occupancyは依然として process-local。
    assert isinstance(stores.activity_projection_store, InMemoryActivityProjectionStore)
    assert isinstance(stores.presence_store, InMemoryPresenceStore)
    assert isinstance(stores.space_occupancy_store, InMemorySpaceOccupancyStore)
