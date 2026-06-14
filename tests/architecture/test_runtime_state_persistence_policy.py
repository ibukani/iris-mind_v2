"""Runtime state永続化policyを強制するarchitecture guard。"""

from __future__ import annotations

from iris.runtime.wiring.state_policy import runtime_state_persistence_policy


def test_sqlite_backend_does_not_make_all_runtime_state_durable() -> None:
    """SQLite backend must not mark every runtime state durable."""
    policy = runtime_state_persistence_policy("sqlite")

    assert policy.account_store == "durable"
    assert policy.memory_store == "durable"
    assert policy.activity_journal == "durable"
    assert policy.activity_projection_store != "durable"
    assert policy.presence_store != "durable"
    assert policy.space_occupancy_store != "durable"
    assert policy.space_binding_store != "durable"


def test_presence_and_space_occupancy_are_not_marked_durable() -> None:
    """Presence and space occupancy are not marked durable."""
    policy = runtime_state_persistence_policy("sqlite")

    assert policy.presence_store == "ephemeral"
    assert policy.space_occupancy_store == "ephemeral"


def test_activity_journal_is_durable_but_projection_is_ephemeral() -> None:
    """Activity journal is durable while projection stays ephemeral."""
    policy = runtime_state_persistence_policy("sqlite")

    assert policy.activity_journal == "durable"
    assert policy.activity_projection_store == "ephemeral"


def test_memory_backend_marks_all_hot_state_ephemeral() -> None:
    """Memory backend keeps every hot state ephemeral."""
    policy = runtime_state_persistence_policy("memory")

    assert policy.account_store == "ephemeral"
    assert policy.memory_store == "ephemeral"
    assert policy.activity_journal == "ephemeral"
    assert policy.activity_projection_store == "ephemeral"
    assert policy.presence_store == "ephemeral"
    assert policy.space_occupancy_store == "ephemeral"
