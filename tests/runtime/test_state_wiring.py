"""Runtime state wiring backend selection tests."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from iris.adapters.sqlite.delivery_outbox import SQLiteDeliveryOutbox
from iris.adapters.sqlite.scheduler_target_store import SQLiteSchedulerTargetStore
from iris.runtime.config import default_runtime_config
from iris.runtime.config.state import RuntimeStateBackend, RuntimeStateConfig
from iris.runtime.delivery.in_memory import InMemoryDeliveryOutbox
from iris.runtime.state.scheduler_targets import InMemorySchedulerTargetStore
from iris.runtime.wiring.state import wire_runtime_state

if TYPE_CHECKING:
    from pathlib import Path


def test_state_wiring_memory_uses_process_local_delivery_and_scheduler_stores() -> None:
    """Memory backend wires process-local outbox and scheduler targets."""
    stores = wire_runtime_state(default_runtime_config())

    assert isinstance(stores.delivery_outbox, InMemoryDeliveryOutbox)
    assert isinstance(stores.scheduler_target_store, InMemorySchedulerTargetStore)


def test_state_wiring_sqlite_uses_durable_delivery_and_scheduler_stores(
    tmp_path: Path,
) -> None:
    """SQLite backend wires durable outbox and scheduler targets."""
    config = replace(
        default_runtime_config(),
        state=RuntimeStateConfig(
            backend=RuntimeStateBackend.SQLITE,
            sqlite_path=str(tmp_path / "state.sqlite3"),
        ),
    )

    stores = wire_runtime_state(config)

    assert isinstance(stores.delivery_outbox, SQLiteDeliveryOutbox)
    assert isinstance(stores.scheduler_target_store, SQLiteSchedulerTargetStore)
