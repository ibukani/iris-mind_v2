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
from iris.runtime.activity.sqlite_journal import SQLiteActivityJournal
from iris.runtime.delivery.in_memory import InMemoryDeliveryOutbox
from iris.runtime.presence.store import InMemoryPresenceStore
from iris.runtime.proactive.targets import InMemoryProactiveTargetStore
from iris.runtime.spaces.occupancy_store import InMemorySpaceOccupancyStore

if TYPE_CHECKING:
    from iris.adapters.app_gateway.ports import AccountStore
    from iris.adapters.memory.ports import MutableMemoryStore
    from iris.runtime.activity.journal import ActivityJournal
    from iris.runtime.activity.projections import ActivityProjectionStore
    from iris.runtime.config import IrisRuntimeConfig
    from iris.runtime.delivery.outbox import DeliveryOutbox
    from iris.runtime.presence.store import PresenceStore
    from iris.runtime.proactive.targets import ProactiveTargetStore
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
    delivery_outbox: DeliveryOutbox
    proactive_target_store: ProactiveTargetStore


def wire_runtime_state(config: IrisRuntimeConfig) -> RuntimeStateStores:
    """永続状態ストアとプロセス内ランタイムstateストアを組み立てる。

    Returns:
        構成済みの RuntimeStateStores。
    """
    if config.state.backend == "sqlite":
        account_store: AccountStore = SQLiteAccountStore(config.state.sqlite_path)
        memory_store: MutableMemoryStore = SQLiteMemoryStore(config.state.sqlite_path)
        activity_journal: ActivityJournal = SQLiteActivityJournal(config.state.sqlite_path)
    else:
        account_store = InMemoryAccountStore()
        memory_store = InMemoryMemoryStore()
        activity_journal = InMemoryActivityJournal()

    return RuntimeStateStores(
        account_store=account_store,
        memory_store=memory_store,
        activity_journal=activity_journal,
        activity_projection_store=InMemoryActivityProjectionStore(),
        presence_store=InMemoryPresenceStore(),
        space_occupancy_store=InMemorySpaceOccupancyStore(),
        delivery_outbox=InMemoryDeliveryOutbox(
            max_depth_per_provider=config.delivery.max_outbox_depth_per_provider,
        ),
        proactive_target_store=InMemoryProactiveTargetStore(),
    )
