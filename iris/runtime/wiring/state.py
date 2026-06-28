"""ランタイム状態と永続化のワイヤリング。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.adapters.persistence.sqlite.context import SQLitePersistenceContext
from iris.adapters.persistence.sqlite.engine import AsyncDatabaseManager
from iris.adapters.persistence.sqlite.stores.account import SQLiteAccountStore
from iris.adapters.persistence.sqlite.stores.activity_journal import SQLiteActivityJournal
from iris.adapters.persistence.sqlite.stores.affect import SQLiteAffectStore
from iris.adapters.persistence.sqlite.stores.delivery_outbox import SQLiteDeliveryOutbox
from iris.adapters.persistence.sqlite.stores.memory import SQLiteMemoryStore
from iris.adapters.persistence.sqlite.stores.relationship import SQLiteRelationshipStore
from iris.adapters.persistence.sqlite.stores.scheduler_targets import SQLiteSchedulerTargetStore
from iris.runtime.config.state import RuntimeStateBackend
from iris.runtime.delivery.in_memory import InMemoryDeliveryOutbox
from iris.runtime.state.activity_journal import InMemoryActivityJournal
from iris.runtime.state.activity_projection import InMemoryActivityProjectionStore
from iris.runtime.state.ephemeral.accounts import InMemoryAccountStore
from iris.runtime.state.ephemeral.affect import InMemoryAffectStore
from iris.runtime.state.ephemeral.relationship import InMemoryRelationshipStore
from iris.runtime.state.presence import InMemoryPresenceStore
from iris.runtime.state.scheduler_targets import InMemorySchedulerTargetStore
from iris.runtime.state.space_occupancy import InMemorySpaceOccupancyStore

if TYPE_CHECKING:
    from iris.contracts.accounts import AccountStore
    from iris.contracts.affect import AffectStore
    from iris.contracts.memory import MutableMemoryStore
    from iris.contracts.relationship import RelationshipStore
    from iris.runtime.config import IrisRuntimeConfig
    from iris.runtime.delivery.outbox import DeliveryOutbox
    from iris.runtime.state.activity_journal import ActivityJournal
    from iris.runtime.state.activity_projection import ActivityProjectionStore
    from iris.runtime.state.presence import PresenceStore
    from iris.runtime.state.scheduler_targets import SchedulerTargetStore
    from iris.runtime.state.space_occupancy import SpaceOccupancyStore


@dataclass(frozen=True)
class RuntimeStateStores:
    """ランタイム状態ストア群。"""

    account_store: AccountStore
    memory_store: MutableMemoryStore
    relationship_store: RelationshipStore
    affect_store: AffectStore
    activity_journal: ActivityJournal
    activity_projection_store: ActivityProjectionStore
    presence_store: PresenceStore
    space_occupancy_store: SpaceOccupancyStore
    delivery_outbox: DeliveryOutbox
    scheduler_target_store: SchedulerTargetStore
    sqlite_context: SQLitePersistenceContext | None = None

    async def close(self) -> None:
        """Close all persistent store connections."""
        if hasattr(self.memory_store, "close"):
            self.memory_store.close()

        if self.sqlite_context is not None:
            await self.sqlite_context.close()


def wire_runtime_state(config: IrisRuntimeConfig) -> RuntimeStateStores:
    """永続状態ストアとプロセス内ランタイム state ストアを組み立てる。

    Returns:
        構成済みの RuntimeStateStores。
    """
    if config.state.backend is RuntimeStateBackend.SQLITE:
        sqlite_path = config.state.sqlite_path
        db_manager = AsyncDatabaseManager(sqlite_path)
        ctx = SQLitePersistenceContext(db=db_manager)

        account_store: AccountStore = SQLiteAccountStore(ctx)
        memory_store: MutableMemoryStore = SQLiteMemoryStore(sqlite_path)
        relationship_store: RelationshipStore = SQLiteRelationshipStore(ctx)
        affect_store: AffectStore = SQLiteAffectStore(ctx)
        activity_journal: ActivityJournal = SQLiteActivityJournal(ctx)
        delivery_outbox: DeliveryOutbox = SQLiteDeliveryOutbox(
            ctx,
            max_depth_per_provider=config.delivery.max_outbox_depth_per_provider,
        )
        scheduler_target_store: SchedulerTargetStore = SQLiteSchedulerTargetStore(ctx)
        sqlite_context = ctx
    else:
        account_store = InMemoryAccountStore()
        memory_store = InMemoryMemoryStore()
        relationship_store = InMemoryRelationshipStore()
        affect_store = InMemoryAffectStore()
        activity_journal = InMemoryActivityJournal()
        delivery_outbox = InMemoryDeliveryOutbox(
            max_depth_per_provider=config.delivery.max_outbox_depth_per_provider,
        )
        scheduler_target_store = InMemorySchedulerTargetStore()
        sqlite_context = None

    return RuntimeStateStores(
        account_store=account_store,
        memory_store=memory_store,
        relationship_store=relationship_store,
        affect_store=affect_store,
        activity_journal=activity_journal,
        activity_projection_store=InMemoryActivityProjectionStore(),
        presence_store=InMemoryPresenceStore(),
        space_occupancy_store=InMemorySpaceOccupancyStore(),
        delivery_outbox=delivery_outbox,
        scheduler_target_store=scheduler_target_store,
        sqlite_context=sqlite_context,
    )
