"""Runtime wiring helper tests for state stores."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.adapters.persistence.sqlite.migrator import SQLiteMigrationResult, SQLiteSchemaMigrator
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
from iris.runtime.config import default_runtime_config
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
from iris.runtime.wiring.state import wire_runtime_state

if TYPE_CHECKING:
    from pathlib import Path


def test_wire_runtime_state_uses_in_memory_runtime_context_stores_by_default() -> None:
    """デフォルトバックエンドでは runtime context store も in-memory になる。"""
    stores = wire_runtime_state(default_runtime_config())

    assert isinstance(stores.account_store, InMemoryAccountStore)
    assert isinstance(stores.memory_store, InMemoryMemoryStore)
    assert isinstance(stores.relationship_store, InMemoryRelationshipStore)
    assert isinstance(stores.affect_store, InMemoryAffectStore)
    assert isinstance(stores.activity_journal, InMemoryActivityJournal)
    assert isinstance(stores.activity_projection_store, InMemoryActivityProjectionStore)
    assert isinstance(stores.presence_store, InMemoryPresenceStore)
    assert isinstance(stores.space_occupancy_store, InMemorySpaceOccupancyStore)
    assert isinstance(stores.background_job_queue, InMemoryBackgroundJobQueue)
    assert isinstance(stores.memory_candidate_review_store, InMemoryMemoryCandidateReviewStore)


@pytest.mark.anyio
async def test_wire_runtime_state_promotes_activity_journal_to_sqlite_under_sqlite(
    tmp_path: Path,
) -> None:
    """SQLite バックエンド選択時、activity journal は durable な SQLite 実装になる。

    永続化policy: ``state.backend = "sqlite"`` 選択時、account、memory、activity
    journalがSQLiteへ永続化される。Activity projection、presence、space occupancyは
    process-localのin-memory実装のままとなる。
    """
    db_path = tmp_path / "state.db"
    config = default_runtime_config()
    config = replace(
        config,
        state=RuntimeStateConfig(backend=RuntimeStateBackend.SQLITE, sqlite_path=str(db_path)),
    )

    stores = wire_runtime_state(config)

    assert isinstance(stores.account_store, SQLiteAccountStore)
    assert isinstance(stores.memory_store, SQLiteMemoryStore)
    assert isinstance(stores.relationship_store, SQLiteRelationshipStore)
    assert isinstance(stores.affect_store, SQLiteAffectStore)
    assert isinstance(stores.activity_journal, SQLiteActivityJournal)
    # projection、presence、space occupancyは依然として process-local。
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

    await stores.close()


@pytest.mark.anyio
async def test_wire_runtime_state_runs_sqlite_schema_migration_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SQLite runtime wiring は context entrypoint で schema migration を一度だけ実行する。"""
    db_path = tmp_path / "state.db"
    config = replace(
        default_runtime_config(),
        state=RuntimeStateConfig(backend=RuntimeStateBackend.SQLITE, sqlite_path=str(db_path)),
    )
    calls: list[str] = []
    original_ensure_current = SQLiteSchemaMigrator.ensure_current

    def counted_ensure_current(
        self: SQLiteSchemaMigrator,
        db_path: str | Path,
    ) -> SQLiteMigrationResult:
        calls.append(str(db_path))
        return original_ensure_current(self, db_path)

    monkeypatch.setattr(SQLiteSchemaMigrator, "ensure_current", counted_ensure_current)

    stores = wire_runtime_state(config)

    assert calls == [str(db_path)]
    await stores.close()
