"""ランタイム状態と永続化のワイヤリング。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.adapters.accounts.memory import InMemoryAccountStore
from iris.adapters.accounts.sqlite import SQLiteAccountStore
from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.adapters.memory.sqlite import SQLiteMemoryStore
from iris.runtime.delivery.in_memory import InMemoryDeliveryOutbox
from iris.runtime.state.activity_journal import InMemoryActivityJournal
from iris.runtime.state.activity_projection import InMemoryActivityProjectionStore
from iris.runtime.state.presence import InMemoryPresenceStore
from iris.runtime.state.proactive_targets import InMemoryProactiveTargetStore
from iris.runtime.state.space_occupancy import InMemorySpaceOccupancyStore
from iris.runtime.state.sqlite_activity_journal import SQLiteActivityJournal

if TYPE_CHECKING:
    from iris.adapters.app_gateway.ports import AccountStore
    from iris.adapters.memory.ports import MutableMemoryStore
    from iris.runtime.config import IrisRuntimeConfig
    from iris.runtime.delivery.outbox import DeliveryOutbox
    from iris.runtime.state.activity_journal import ActivityJournal
    from iris.runtime.state.activity_projection import ActivityProjectionStore
    from iris.runtime.state.presence import PresenceStore
    from iris.runtime.state.proactive_targets import ProactiveTargetStore
    from iris.runtime.state.space_occupancy import SpaceOccupancyStore


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
