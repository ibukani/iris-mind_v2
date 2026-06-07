"""Tests for runtime state wiring."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from iris.adapters.accounts.memory import InMemoryAccountStore
from iris.adapters.accounts.sqlite import SQLiteAccountStore
from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.adapters.memory.sqlite import SQLiteMemoryStore
from iris.runtime.config import default_runtime_config
from iris.runtime.config.state import RuntimeStateConfig
from iris.runtime.wiring.state import wire_runtime_state

if TYPE_CHECKING:
    from pathlib import Path


def test_wire_memory_backend() -> None:
    """Test wiring with memory backend."""
    config = default_runtime_config()
    stores = wire_runtime_state(config)
    assert isinstance(stores.account_store, InMemoryAccountStore)
    assert isinstance(stores.memory_store, InMemoryMemoryStore)


def test_wire_sqlite_backend(tmp_path: Path) -> None:
    """Test wiring with sqlite backend."""
    db_path = tmp_path / "state.db"
    config = default_runtime_config()
    config = replace(config, state=RuntimeStateConfig(backend="sqlite", sqlite_path=str(db_path)))
    stores = wire_runtime_state(config)
    assert isinstance(stores.account_store, SQLiteAccountStore)
    assert isinstance(stores.memory_store, SQLiteMemoryStore)
    assert db_path.exists()


def test_wire_memory_backend_uses_independent_stores() -> None:
    """Memory backend provides fresh, independent stores per call."""
    config = default_runtime_config()
    stores_a = wire_runtime_state(config)
    stores_b = wire_runtime_state(config)

    assert stores_a.memory_store is not stores_b.memory_store
    assert stores_a.account_store is not stores_b.account_store
