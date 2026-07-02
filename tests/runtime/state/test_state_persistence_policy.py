"""Runtime state永続化policyのテスト。"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.adapters.persistence.sqlite.stores.account import SQLiteAccountStore
from iris.adapters.persistence.sqlite.stores.activity_journal import SQLiteActivityJournal
from iris.adapters.persistence.sqlite.stores.affect import SQLiteAffectStore
from iris.adapters.persistence.sqlite.stores.background_jobs import SQLiteBackgroundJobQueue
from iris.adapters.persistence.sqlite.stores.memory import SQLiteMemoryStore
from iris.adapters.persistence.sqlite.stores.memory_candidate_reviews import (
    SQLiteMemoryCandidateReviewStore,
)
from iris.adapters.persistence.sqlite.stores.relationship import SQLiteRelationshipStore
from iris.adapters.persistence.sqlite.stores.scheduler_targets import SQLiteSchedulerTargetStore
from iris.adapters.persistence.sqlite.stores.transcript import SQLiteTranscriptStore
from iris.runtime.config import ConfigError, default_runtime_config
from iris.runtime.config.conversation import RuntimeConversationConfig, RuntimeTranscriptConfig
from iris.runtime.config.state import RuntimeStateBackend, RuntimeStateConfig
from iris.runtime.learning.queue import InMemoryBackgroundJobQueue
from iris.runtime.state.activity_journal import InMemoryActivityJournal
from iris.runtime.state.activity_projection import InMemoryActivityProjectionStore
from iris.runtime.state.ephemeral.accounts import InMemoryAccountStore
from iris.runtime.state.ephemeral.affect import InMemoryAffectStore
from iris.runtime.state.ephemeral.relationship import InMemoryRelationshipStore
from iris.runtime.state.memory_candidates import InMemoryMemoryCandidateReviewStore
from iris.runtime.state.presence import InMemoryPresenceStore
from iris.runtime.state.space_occupancy import InMemorySpaceOccupancyStore
from iris.runtime.state.transcript import NullTranscriptStore
from iris.runtime.wiring.state import wire_runtime_state
from iris.runtime.wiring.state_policy import (
    PERSISTENCE_KIND_VALUES,
    PersistenceKind,
    runtime_state_persistence_policy,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_memory_backend_policy_marks_runtime_state_ephemeral() -> None:
    """Memory backend marks runtime state stores ephemeral."""
    policy = runtime_state_persistence_policy(RuntimeStateBackend.MEMORY)

    assert policy.account_store == PersistenceKind.EPHEMERAL
    assert policy.memory_store == PersistenceKind.EPHEMERAL
    assert policy.activity_journal == PersistenceKind.EPHEMERAL
    assert policy.activity_projection_store == PersistenceKind.EPHEMERAL
    assert policy.presence_store == PersistenceKind.EPHEMERAL
    assert policy.space_occupancy_store == PersistenceKind.EPHEMERAL
    assert policy.relationship_store == PersistenceKind.EPHEMERAL
    assert policy.affect_store == PersistenceKind.EPHEMERAL
    assert policy.delivery_outbox == PersistenceKind.EPHEMERAL
    assert policy.scheduler_target_store == PersistenceKind.EPHEMERAL
    assert policy.background_job_queue == PersistenceKind.EPHEMERAL
    assert policy.memory_candidate_review_store == PersistenceKind.EPHEMERAL
    assert policy.transcript_store == PersistenceKind.EPHEMERAL


def test_sqlite_backend_policy_marks_durable_companion_state() -> None:
    """SQLite backend marks companion state and activity journal durable."""
    policy = runtime_state_persistence_policy(RuntimeStateBackend.SQLITE)

    assert policy.account_store == PersistenceKind.DURABLE
    assert policy.memory_store == PersistenceKind.DURABLE
    assert policy.relationship_store == PersistenceKind.DURABLE
    assert policy.affect_store == PersistenceKind.DURABLE
    assert policy.activity_journal == PersistenceKind.DURABLE
    assert policy.delivery_outbox == PersistenceKind.DURABLE
    assert policy.scheduler_target_store == PersistenceKind.DURABLE
    assert policy.background_job_queue == PersistenceKind.DURABLE
    assert policy.memory_candidate_review_store == PersistenceKind.DURABLE
    assert policy.transcript_store == PersistenceKind.DEFERRED


def test_sqlite_backend_keeps_runtime_projections_ephemeral() -> None:
    """SQLite backend keeps volatile runtime projections ephemeral."""
    policy = runtime_state_persistence_policy(RuntimeStateBackend.SQLITE)

    assert policy.activity_projection_store == PersistenceKind.EPHEMERAL
    assert policy.presence_store == PersistenceKind.EPHEMERAL
    assert policy.space_occupancy_store == PersistenceKind.EPHEMERAL


@pytest.mark.anyio
async def test_sqlite_runtime_wiring_uses_sqlite_durable_stores(tmp_path: Path) -> None:
    """SQLite backend wiring produces SQLite durable stores."""
    config = replace(
        default_runtime_config(),
        state=RuntimeStateConfig(
            backend=RuntimeStateBackend.SQLITE, sqlite_path=str(tmp_path / "state.db")
        ),
    )

    stores = wire_runtime_state(config)

    assert isinstance(stores.account_store, SQLiteAccountStore)
    assert isinstance(stores.memory_store, SQLiteMemoryStore)
    assert isinstance(stores.relationship_store, SQLiteRelationshipStore)
    assert isinstance(stores.affect_store, SQLiteAffectStore)
    assert isinstance(stores.activity_journal, SQLiteActivityJournal)
    assert isinstance(stores.scheduler_target_store, SQLiteSchedulerTargetStore)
    assert isinstance(stores.background_job_queue, SQLiteBackgroundJobQueue)
    assert isinstance(stores.memory_candidate_review_store, SQLiteMemoryCandidateReviewStore)
    assert isinstance(stores.transcript_store, NullTranscriptStore)

    await stores.close()


def test_memory_runtime_wiring_uses_in_memory_state_stores() -> None:
    """Memory backend wiring produces in-memory stores."""
    stores = wire_runtime_state(default_runtime_config())

    assert isinstance(stores.account_store, InMemoryAccountStore)
    assert isinstance(stores.memory_store, InMemoryMemoryStore)
    assert isinstance(stores.relationship_store, InMemoryRelationshipStore)
    assert isinstance(stores.affect_store, InMemoryAffectStore)
    assert isinstance(stores.activity_journal, InMemoryActivityJournal)
    assert isinstance(stores.background_job_queue, InMemoryBackgroundJobQueue)
    assert isinstance(stores.memory_candidate_review_store, InMemoryMemoryCandidateReviewStore)
    assert isinstance(stores.transcript_store, NullTranscriptStore)


def test_memory_runtime_wiring_rejects_enabled_transcript_store() -> None:
    """Memory backend で transcript persistence を有効化すると fail closed する。"""
    config = replace(
        default_runtime_config(),
        conversation=RuntimeConversationConfig(
            transcript=RuntimeTranscriptConfig(enabled=True),
        ),
    )

    with pytest.raises(ConfigError, match=r"state\.backend='sqlite'"):
        wire_runtime_state(config)


@pytest.mark.anyio
async def test_runtime_wiring_keeps_projection_presence_and_occupancy_in_memory(
    tmp_path: Path,
) -> None:
    """SQLite backend keeps projections, presence, and occupancy in memory."""
    config = replace(
        default_runtime_config(),
        state=RuntimeStateConfig(
            backend=RuntimeStateBackend.SQLITE, sqlite_path=str(tmp_path / "state.db")
        ),
    )

    stores = wire_runtime_state(config)

    assert isinstance(stores.activity_projection_store, InMemoryActivityProjectionStore)
    assert isinstance(stores.presence_store, InMemoryPresenceStore)
    assert isinstance(stores.space_occupancy_store, InMemorySpaceOccupancyStore)
    assert isinstance(stores.account_store, SQLiteAccountStore)
    assert isinstance(stores.memory_store, SQLiteMemoryStore)
    assert isinstance(stores.relationship_store, SQLiteRelationshipStore)
    assert isinstance(stores.affect_store, SQLiteAffectStore)
    assert isinstance(stores.activity_journal, SQLiteActivityJournal)
    assert isinstance(stores.scheduler_target_store, SQLiteSchedulerTargetStore)
    assert isinstance(stores.background_job_queue, SQLiteBackgroundJobQueue)
    assert isinstance(stores.memory_candidate_review_store, SQLiteMemoryCandidateReviewStore)
    assert isinstance(stores.transcript_store, NullTranscriptStore)

    await stores.close()


def test_persistence_kind_literal_values_include_deferred_for_policy_docs() -> None:
    """PersistenceKind values remain stable for policy documentation."""
    assert PERSISTENCE_KIND_VALUES == ("durable", "ephemeral", "deferred")


@pytest.mark.anyio
async def test_sqlite_runtime_wiring_uses_sqlite_transcript_store_when_enabled(
    tmp_path: Path,
) -> None:
    """SQLite transcript store は明示 enabled の場合だけ durable store になる。"""
    base = default_runtime_config()
    config = replace(
        base,
        state=RuntimeStateConfig(
            backend=RuntimeStateBackend.SQLITE,
            sqlite_path=str(tmp_path / "state.db"),
        ),
        conversation=RuntimeConversationConfig(
            transcript=RuntimeTranscriptConfig(enabled=True),
        ),
    )

    stores = wire_runtime_state(config)

    assert isinstance(stores.transcript_store, SQLiteTranscriptStore)

    await stores.close()
