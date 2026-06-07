"""ランタイム状態と永続化のワイヤリング。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.adapters.accounts.memory import InMemoryAccountStore
from iris.adapters.accounts.sqlite import SQLiteAccountStore
from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.adapters.memory.sqlite import SQLiteMemoryStore

if TYPE_CHECKING:
    from iris.adapters.app_gateway.ports import AccountStore
    from iris.adapters.memory.ports import MutableMemoryStore
    from iris.runtime.config import IrisRuntimeConfig


@dataclass(frozen=True)
class RuntimeStateStores:
    """ランタイム向けに組み立てられた永続ストア。"""

    account_store: AccountStore
    memory_store: MutableMemoryStore


def wire_runtime_state(config: IrisRuntimeConfig) -> RuntimeStateStores:
    """永続状態ストアを組み立てて初期化する。

    Args:
        config: ランタイム設定全体。

    Returns:
        構成済みのランタイム状態ストア。
    """
    if config.state.backend == "sqlite":
        account_store: AccountStore = SQLiteAccountStore(config.state.sqlite_path)
        memory_store: MutableMemoryStore = SQLiteMemoryStore(config.state.sqlite_path)
    else:
        account_store = InMemoryAccountStore()
        memory_store = InMemoryMemoryStore()

    return RuntimeStateStores(account_store=account_store, memory_store=memory_store)
