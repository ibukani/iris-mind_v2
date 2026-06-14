"""Runtime state永続化policyのテスト。"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from iris.adapters.accounts.memory import InMemoryAccountStore
from iris.adapters.accounts.sqlite import SQLiteAccountStore
from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.adapters.memory.sqlite import SQLiteMemoryStore
from iris.runtime.activity.journal import InMemoryActivityJournal
from iris.runtime.activity.projections import InMemoryActivityProjectionStore
from iris.runtime.activity.sqlite_journal import SQLiteActivityJournal
from iris.runtime.config import default_runtime_config
from iris.runtime.config.state import RuntimeStateConfig
from iris.runtime.presence.store import InMemoryPresenceStore
from iris.runtime.spaces.occupancy_store import InMemorySpaceOccupancyStore
from iris.runtime.wiring.state import wire_runtime_state
from iris.runtime.wiring.state_policy import (
    PERSISTENCE_KIND_VALUES,
    runtime_state_persistence_policy,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_memory_backend_policy_marks_runtime_state_ephemeral() -> None:
    """Memory backend marks all runtime state as ephemeral."""
    policy = runtime_state_persistence_policy("memory")

    assert policy.account_store == "ephemeral"
    assert policy.memory_store == "ephemeral"
    assert policy.activity_journal == "ephemeral"


def test_sqlite_backend_policy_marks_account_memory_and_activity_journal_durable() -> None:
    """SQLite backend marks account, memory, and activity journal as durable."""
    policy = runtime_state_persistence_policy("sqlite")

    assert policy.account_store == "durable"
    assert policy.memory_store == "durable"
    assert policy.activity_journal == "durable"


def test_sqlite_backend_policy_keeps_activity_projection_ephemeral() -> None:
    """SQLite backend keeps activity projection ephemeral."""
    policy = runtime_state_persistence_policy("sqlite")

    assert policy.activity_projection_store == "ephemeral"


def test_sqlite_backend_policy_keeps_presence_ephemeral() -> None:
    """SQLite backend keeps presence ephemeral."""
    policy = runtime_state_persistence_policy("sqlite")

    assert policy.presence_store == "ephemeral"


def test_sqlite_backend_policy_keeps_space_occupancy_ephemeral() -> None:
    """SQLite backend keeps space occupancy ephemeral."""
    policy = runtime_state_persistence_policy("sqlite")

    assert policy.space_occupancy_store == "ephemeral"


def test_sqlite_backend_policy_keeps_space_binding_ephemeral() -> None:
    """SQLite backend keeps ephemeral space binding ephemeral."""
    policy = runtime_state_persistence_policy("sqlite")

    assert policy.space_binding_store == "ephemeral"


def test_sqlite_backend_policy_marks_relationship_and_affect_deferred() -> None:
    """Relationship and affect are deferred durability targets."""
    policy = runtime_state_persistence_policy("sqlite")

    assert policy.relationship_store == "deferred"
    assert policy.affect_store == "deferred"


def test_sqlite_runtime_wiring_uses_sqlite_activity_journal(tmp_path: Path) -> None:
    """SQLite backend wiring produces a SQLiteActivityJournal."""
    config = replace(
        default_runtime_config(),
        state=RuntimeStateConfig(backend="sqlite", sqlite_path=str(tmp_path / "state.db")),
    )

    stores = wire_runtime_state(config)

    assert isinstance(stores.account_store, SQLiteAccountStore)
    assert isinstance(stores.memory_store, SQLiteMemoryStore)
    assert isinstance(stores.activity_journal, SQLiteActivityJournal)


def test_memory_runtime_wiring_uses_in_memory_activity_journal() -> None:
    """Memory backend wiring produces an InMemoryActivityJournal."""
    config = default_runtime_config()

    stores = wire_runtime_state(config)

    assert isinstance(stores.account_store, InMemoryAccountStore)
    assert isinstance(stores.memory_store, InMemoryMemoryStore)
    assert isinstance(stores.activity_journal, InMemoryActivityJournal)


def test_sqlite_runtime_wiring_keeps_projection_presence_and_occupancy_in_memory(
    tmp_path: Path,
) -> None:
    """SQLite backend keeps projection, presence, and occupancy in-memory."""
    config = replace(
        default_runtime_config(),
        state=RuntimeStateConfig(backend="sqlite", sqlite_path=str(tmp_path / "state.db")),
    )

    stores = wire_runtime_state(config)

    assert isinstance(stores.activity_projection_store, InMemoryActivityProjectionStore)
    assert isinstance(stores.presence_store, InMemoryPresenceStore)
    assert isinstance(stores.space_occupancy_store, InMemorySpaceOccupancyStore)


def test_persistence_kind_literal_values() -> None:
    """PersistenceKind accepts only durable/ephemeral/deferred."""
    assert PERSISTENCE_KIND_VALUES == ("durable", "ephemeral", "deferred")
