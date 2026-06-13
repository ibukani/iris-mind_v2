"""ランタイム状態と永続化のワイヤリング。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.adapters.accounts.memory import InMemoryAccountStore
from iris.adapters.accounts.sqlite import SQLiteAccountStore
from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.adapters.memory.sqlite import SQLiteMemoryStore
from iris.runtime.activity.journal import InMemoryActivityJournal
from iris.runtime.activity.projections import InMemoryActivityProjectionStore
from iris.runtime.presence.store import InMemoryPresenceStore
from iris.runtime.spaces.occupancy_store import InMemorySpaceOccupancyStore

if TYPE_CHECKING:
    from iris.adapters.app_gateway.ports import AccountStore
    from iris.adapters.memory.ports import MutableMemoryStore
    from iris.runtime.activity.journal import ActivityJournal
    from iris.runtime.activity.projections import ActivityProjectionStore
    from iris.runtime.config import IrisRuntimeConfig
    from iris.runtime.presence.store import PresenceStore
    from iris.runtime.spaces.occupancy_store import SpaceOccupancyStore


@dataclass(frozen=True)
class RuntimeStateStores:
    """ランタイム向けに組み立てられた永続ストアとランタイムstateストア。"""

    account_store: AccountStore
    memory_store: MutableMemoryStore
    activity_journal: ActivityJournal
    activity_projection_store: ActivityProjectionStore
    presence_store: PresenceStore
    space_occupancy_store: SpaceOccupancyStore


def wire_runtime_state(config: IrisRuntimeConfig) -> RuntimeStateStores:
    """永続状態ストアとプロセス内ランタイムstateストアを組み立てて初期化する。

    Args:
        config: ランタイム設定。

    Returns:
        RuntimeStateStores: ランタイムが使うストア群。
    """
    if config.state.backend == "sqlite":
        account_store: AccountStore = SQLiteAccountStore(config.state.sqlite_path)
        memory_store: MutableMemoryStore = SQLiteMemoryStore(config.state.sqlite_path)
    else:
        account_store = InMemoryAccountStore()
        memory_store = InMemoryMemoryStore()

    activity_journal: ActivityJournal = InMemoryActivityJournal()
    activity_projection_store: ActivityProjectionStore = InMemoryActivityProjectionStore()
    presence_store: PresenceStore = InMemoryPresenceStore()
    space_occupancy_store: SpaceOccupancyStore = InMemorySpaceOccupancyStore()

    return RuntimeStateStores(
        account_store=account_store,
        memory_store=memory_store,
        activity_journal=activity_journal,
        activity_projection_store=activity_projection_store,
        presence_store=presence_store,
        space_occupancy_store=space_occupancy_store,
    )
