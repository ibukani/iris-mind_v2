"""Runtime state永続化policyのテスト。"""

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
from iris.runtime.config.state import RuntimeStateBackend, RuntimeStateConfig
from iris.runtime.state.activity_journal import InMemoryActivityJournal
from iris.runtime.state.activity_projection import InMemoryActivityProjectionStore
from iris.runtime.state.presence import InMemoryPresenceStore
from iris.runtime.state.space_occupancy import InMemorySpaceOccupancyStore
from iris.runtime.wiring.state import wire_runtime_state
from iris.runtime.wiring.state_policy import (
    PERSISTENCE_KIND_VALUES,
    PersistenceKind,
    runtime_state_persistence_policy,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_memory_backend_policy_marks_runtime_state_ephemeral() -> None:
    """Memory backend marks runtime state stores ephemeral."""
    policy = runtime_state_persistence_policy(RuntimeStateBackend.MEMORY)

    assert policy.account_store == PersistenceKind.EPHEMERAL
    assert policy.memory_store == PersistenceKind.EPHEMERAL
    assert policy.activity_journal == PersistenceKind.EPHEMERAL
    assert policy.activity_projection_store == PersistenceKind.EPHEMERAL
    assert policy.presence_store == PersistenceKind.EPHEMERAL
    assert policy.space_occupancy_store == PersistenceKind.EPHEMERAL
    assert policy.relationship_store == PersistenceKind.EPHEMERAL
    assert policy.affect_store == PersistenceKind.EPHEMERAL


def test_sqlite_backend_policy_marks_durable_companion_state() -> None:
    """SQLite backend marks companion state and activity journal durable."""
    policy = runtime_state_persistence_policy(RuntimeStateBackend.SQLITE)

    assert policy.account_store == PersistenceKind.DURABLE
    assert policy.memory_store == PersistenceKind.DURABLE
    assert policy.relationship_store == PersistenceKind.DURABLE
    assert policy.affect_store == PersistenceKind.DURABLE
    assert policy.activity_journal == PersistenceKind.DURABLE


def test_sqlite_backend_keeps_runtime_projections_ephemeral() -> None:
    """SQLite backend keeps volatile runtime projections ephemeral."""
    policy = runtime_state_persistence_policy(RuntimeStateBackend.SQLITE)

    assert policy.activity_projection_store == PersistenceKind.EPHEMERAL
    assert policy.presence_store == PersistenceKind.EPHEMERAL
    assert policy.space_occupancy_store == PersistenceKind.EPHEMERAL


def test_sqlite_runtime_wiring_uses_sqlite_durable_stores(tmp_path: Path) -> None:
    """SQLite backend wiring produces SQLite durable stores."""
    config = replace(
        default_runtime_config(),
        state=RuntimeStateConfig(
            backend=RuntimeStateBackend.SQLITE, sqlite_path=str(tmp_path / "state.db")
        ),
    )

    stores = wire_runtime_state(config)

    assert isinstance(stores.account_store, SQLiteAccountStore)
    assert isinstance(stores.memory_store, SQLiteMemoryStore)
    assert isinstance(stores.relationship_store, SQLiteRelationshipStore)
    assert isinstance(stores.affect_store, SQLiteAffectStore)
    assert isinstance(stores.activity_journal, SQLiteActivityJournal)


def test_memory_runtime_wiring_uses_in_memory_state_stores() -> None:
    """Memory backend wiring produces in-memory stores."""
    stores = wire_runtime_state(default_runtime_config())

    assert isinstance(stores.account_store, InMemoryAccountStore)
    assert isinstance(stores.memory_store, InMemoryMemoryStore)
    assert isinstance(stores.relationship_store, InMemoryRelationshipStore)
    assert isinstance(stores.affect_store, InMemoryAffectStore)
    assert isinstance(stores.activity_journal, InMemoryActivityJournal)


def test_runtime_wiring_keeps_projection_presence_and_occupancy_in_memory(
    tmp_path: Path,
) -> None:
    """SQLite backend keeps projections, presence, and occupancy in memory."""
    config = replace(
        default_runtime_config(),
        state=RuntimeStateConfig(
            backend=RuntimeStateBackend.SQLITE, sqlite_path=str(tmp_path / "state.db")
        ),
    )

    stores = wire_runtime_state(config)

    assert isinstance(stores.activity_projection_store, InMemoryActivityProjectionStore)
    assert isinstance(stores.presence_store, InMemoryPresenceStore)
    assert isinstance(stores.space_occupancy_store, InMemorySpaceOccupancyStore)


def test_persistence_kind_literal_values_include_deferred_for_policy_docs() -> None:
    """PersistenceKind values remain stable for policy documentation."""
    assert PERSISTENCE_KIND_VALUES == ("durable", "ephemeral", "deferred")
