"""Wiring for runtime state and persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.adapters.accounts.memory import InMemoryAccountStore
from iris.adapters.accounts.sqlite import SQLiteAccountStore

if TYPE_CHECKING:
    from iris.adapters.app_gateway.ports import AccountStore
    from iris.runtime.config import IrisRuntimeConfig


@dataclass(frozen=True)
class RuntimeStateStores:
    """Wired persistence stores for the runtime."""

    account_store: AccountStore


def wire_runtime_state(config: IrisRuntimeConfig) -> RuntimeStateStores:
    """Wire and initialize persistent state stores.

    Args:
        config: Full runtime configuration.

    Returns:
        Configured runtime state stores.
    """
    if config.state.backend == "sqlite":
        account_store: AccountStore = SQLiteAccountStore(config.state.sqlite_path)
    else:
        account_store = InMemoryAccountStore()

    return RuntimeStateStores(account_store=account_store)
