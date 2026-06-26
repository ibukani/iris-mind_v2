"""Runtime state永続化policyを強制するarchitecture guard。"""

from __future__ import annotations

from iris.runtime.config.state import RuntimeStateBackend
from iris.runtime.wiring.state_policy import PersistenceKind, runtime_state_persistence_policy


def test_sqlite_backend_does_not_make_all_runtime_state_durable() -> None:
    """SQLite backend must not mark every runtime state durable."""
    policy = runtime_state_persistence_policy(RuntimeStateBackend.SQLITE)

    assert policy.account_store == PersistenceKind.DURABLE
    assert policy.memory_store == PersistenceKind.DURABLE
    assert policy.activity_journal == PersistenceKind.DURABLE
    assert policy.activity_projection_store != PersistenceKind.DURABLE
    assert policy.presence_store != PersistenceKind.DURABLE
    assert policy.space_occupancy_store != PersistenceKind.DURABLE
    assert policy.space_binding_store != PersistenceKind.DURABLE


def test_presence_and_space_occupancy_are_not_marked_durable() -> None:
    """Presence and space occupancy are not marked durable."""
    policy = runtime_state_persistence_policy(RuntimeStateBackend.SQLITE)

    assert policy.presence_store == PersistenceKind.EPHEMERAL
    assert policy.space_occupancy_store == PersistenceKind.EPHEMERAL


def test_activity_journal_is_durable_but_projection_is_ephemeral() -> None:
    """Activity journal is durable while projection stays ephemeral."""
    policy = runtime_state_persistence_policy(RuntimeStateBackend.SQLITE)

    assert policy.activity_journal == PersistenceKind.DURABLE
    assert policy.activity_projection_store == PersistenceKind.EPHEMERAL


def test_memory_backend_marks_all_hot_state_ephemeral() -> None:
    """Memory backend keeps every hot state ephemeral."""
    policy = runtime_state_persistence_policy(RuntimeStateBackend.MEMORY)

    assert policy.account_store == PersistenceKind.EPHEMERAL
    assert policy.memory_store == PersistenceKind.EPHEMERAL
    assert policy.activity_journal == PersistenceKind.EPHEMERAL
    assert policy.activity_projection_store == PersistenceKind.EPHEMERAL
    assert policy.presence_store == PersistenceKind.EPHEMERAL
    assert policy.space_occupancy_store == PersistenceKind.EPHEMERAL
