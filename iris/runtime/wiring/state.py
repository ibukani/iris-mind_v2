"""ランタイム状態と永続化のワイヤリング。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.adapters.persistence.sqlite.context import SQLitePersistenceContext
from iris.adapters.persistence.sqlite.stores.account import SQLiteAccountStore
from iris.adapters.persistence.sqlite.stores.activity_journal import SQLiteActivityJournal
from iris.adapters.persistence.sqlite.stores.affect import SQLiteAffectStore
from iris.adapters.persistence.sqlite.stores.background_jobs import SQLiteBackgroundJobQueue
from iris.adapters.persistence.sqlite.stores.delivery_outbox import SQLiteDeliveryOutbox
from iris.adapters.persistence.sqlite.stores.memory import SQLiteMemoryStore
from iris.adapters.persistence.sqlite.stores.memory_candidate_reviews import (
    SQLiteMemoryCandidateReviewStore,
)
from iris.adapters.persistence.sqlite.stores.relationship import SQLiteRelationshipStore
from iris.adapters.persistence.sqlite.stores.safety_audit import SQLiteSafetyAuditJournal
from iris.adapters.persistence.sqlite.stores.scheduler_targets import SQLiteSchedulerTargetStore
from iris.adapters.persistence.sqlite.stores.transcript import SQLiteTranscriptStore
from iris.runtime.config.errors import ConfigError
from iris.runtime.config.state import RuntimeStateBackend
from iris.runtime.delivery.in_memory import InMemoryDeliveryOutbox
from iris.runtime.learning.dispatch import InMemoryLearningDispatchStore
from iris.runtime.learning.queue import BackgroundJobQueue, InMemoryBackgroundJobQueue
from iris.runtime.state.activity_journal import InMemoryActivityJournal
from iris.runtime.state.activity_projection import InMemoryActivityProjectionStore
from iris.runtime.state.conversation import InMemoryConversationHistoryStore
from iris.runtime.state.ephemeral.accounts import InMemoryAccountStore
from iris.runtime.state.ephemeral.affect import InMemoryAffectStore
from iris.runtime.state.ephemeral.relationship import InMemoryRelationshipStore
from iris.runtime.state.memory_candidates import InMemoryMemoryCandidateReviewStore
from iris.runtime.state.presence import InMemoryPresenceStore
from iris.runtime.state.safety_audit import InMemorySafetyAuditJournal
from iris.runtime.state.scheduler_targets import InMemorySchedulerTargetStore
from iris.runtime.state.space_occupancy import InMemorySpaceOccupancyStore
from iris.runtime.state.transcript import NullTranscriptStore

if TYPE_CHECKING:
    from iris.contracts.accounts import AccountStore
    from iris.contracts.affect import AffectStore
    from iris.contracts.memory import MutableMemoryStore
    from iris.contracts.relationship import RelationshipStore
    from iris.runtime.config import IrisRuntimeConfig
    from iris.runtime.delivery.outbox import DeliveryOutbox
    from iris.runtime.state.activity_journal import ActivityJournal
    from iris.runtime.state.activity_projection import ActivityProjectionStore
    from iris.runtime.state.memory_candidates import MemoryCandidateReviewStore
    from iris.runtime.state.presence import PresenceStore
    from iris.runtime.state.safety_audit import SafetyAuditJournal
    from iris.runtime.state.scheduler_targets import SchedulerTargetStore
    from iris.runtime.state.space_occupancy import SpaceOccupancyStore
    from iris.runtime.state.transcript import TranscriptStore


class SyncLifecycle(Protocol):
    """同期closeを持つ明示的lifecycle境界。"""

    def close(self) -> None:
        """所有resourceを閉じる。"""
        ...


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
    safety_audit_journal: SafetyAuditJournal
    background_job_queue: BackgroundJobQueue
    memory_candidate_review_store: MemoryCandidateReviewStore
    learning_dispatch_store: InMemoryLearningDispatchStore
    conversation_history_store: InMemoryConversationHistoryStore
    transcript_store: TranscriptStore
    sqlite_context: SQLitePersistenceContext | None = None
    sync_lifecycles: tuple[SyncLifecycle, ...] = ()

    async def close(self) -> None:
        """Close all persistent store connections."""
        for lifecycle in self.sync_lifecycles:
            lifecycle.close()

        if self.sqlite_context is not None:
            await self.sqlite_context.close()


def wire_runtime_state(config: IrisRuntimeConfig) -> RuntimeStateStores:
    """永続状態ストアとプロセス内ランタイム state ストアを組み立てる。

    Returns:
        構成済みの RuntimeStateStores。
    """
    if config.state.backend is RuntimeStateBackend.SQLITE:
        return _wire_sqlite_runtime_state(config)
    return _wire_in_memory_runtime_state(config)


def _wire_sqlite_runtime_state(config: IrisRuntimeConfig) -> RuntimeStateStores:
    """SQLite backend 用の永続状態ストア群を組み立てる。

    Learning dispatch と短期会話履歴は process-local のままにする。
    Background job queue と review candidate lifecycle は SQLite で永続化する。
    Transcript は config で明示有効化された場合だけ SQLite に保存する。

    Returns:
        SQLite backend に対応した RuntimeStateStores。
    """
    sqlite_path = config.state.sqlite_path
    ctx = SQLitePersistenceContext.open(sqlite_path)
    sqlite_memory_store = SQLiteMemoryStore(sqlite_path, ensure_schema=False)
    sqlite_background_job_queue = SQLiteBackgroundJobQueue(sqlite_path, ensure_schema=False)
    sqlite_candidate_review_store = SQLiteMemoryCandidateReviewStore(
        sqlite_path,
        ensure_schema=False,
    )
    sqlite_transcript_store = (
        SQLiteTranscriptStore(
            sqlite_path,
            ensure_schema=False,
            max_records_per_key=config.conversation.transcript.max_records_per_key,
        )
        if config.conversation.transcript.enabled
        else None
    )
    memory_store: MutableMemoryStore = sqlite_memory_store
    return RuntimeStateStores(
        account_store=SQLiteAccountStore(ctx),
        memory_store=memory_store,
        relationship_store=SQLiteRelationshipStore(ctx),
        affect_store=SQLiteAffectStore(ctx),
        activity_journal=SQLiteActivityJournal(ctx),
        activity_projection_store=InMemoryActivityProjectionStore(),
        presence_store=InMemoryPresenceStore(),
        space_occupancy_store=InMemorySpaceOccupancyStore(),
        delivery_outbox=SQLiteDeliveryOutbox(
            ctx,
            max_depth_per_provider=config.delivery.max_outbox_depth_per_provider,
        ),
        scheduler_target_store=SQLiteSchedulerTargetStore(ctx),
        safety_audit_journal=SQLiteSafetyAuditJournal(ctx),
        background_job_queue=sqlite_background_job_queue,
        memory_candidate_review_store=sqlite_candidate_review_store,
        learning_dispatch_store=InMemoryLearningDispatchStore(),
        conversation_history_store=InMemoryConversationHistoryStore(),
        transcript_store=sqlite_transcript_store or NullTranscriptStore(),
        sqlite_context=ctx,
        sync_lifecycles=tuple(
            lifecycle
            for lifecycle in (
                sqlite_memory_store,
                sqlite_background_job_queue,
                sqlite_candidate_review_store,
                sqlite_transcript_store,
            )
            if lifecycle is not None
        ),
    )


def _wire_in_memory_runtime_state(config: IrisRuntimeConfig) -> RuntimeStateStores:
    """Process-local backend 用の永続状態ストア群を組み立てる。

    Returns:
        Process-local backend に対応した RuntimeStateStores。

    Raises:
        ConfigError: transcript persistence が memory backend で有効な場合。
    """
    if config.conversation.transcript.enabled:
        message = "conversation.transcript.enabled=true requires state.backend='sqlite'"
        raise ConfigError(message)
    return RuntimeStateStores(
        account_store=InMemoryAccountStore(),
        memory_store=InMemoryMemoryStore(),
        relationship_store=InMemoryRelationshipStore(),
        affect_store=InMemoryAffectStore(),
        activity_journal=InMemoryActivityJournal(),
        activity_projection_store=InMemoryActivityProjectionStore(),
        presence_store=InMemoryPresenceStore(),
        space_occupancy_store=InMemorySpaceOccupancyStore(),
        delivery_outbox=InMemoryDeliveryOutbox(
            max_depth_per_provider=config.delivery.max_outbox_depth_per_provider,
        ),
        scheduler_target_store=InMemorySchedulerTargetStore(),
        safety_audit_journal=InMemorySafetyAuditJournal(),
        background_job_queue=InMemoryBackgroundJobQueue(),
        memory_candidate_review_store=InMemoryMemoryCandidateReviewStore(),
        learning_dispatch_store=InMemoryLearningDispatchStore(),
        conversation_history_store=InMemoryConversationHistoryStore(),
        transcript_store=NullTranscriptStore(),
        sqlite_context=None,
        sync_lifecycles=(),
    )
