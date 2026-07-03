"""runtime state wiring の backend 選択 test。"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from iris.adapters.persistence.sqlite.stores.background_jobs import SQLiteBackgroundJobQueue
from iris.adapters.persistence.sqlite.stores.delivery_outbox import SQLiteDeliveryOutbox
from iris.adapters.persistence.sqlite.stores.memory_candidate_reviews import (
    SQLiteMemoryCandidateReviewStore,
)
from iris.adapters.persistence.sqlite.stores.safety_audit import SQLiteSafetyAuditJournal
from iris.adapters.persistence.sqlite.stores.scheduler_targets import SQLiteSchedulerTargetStore
from iris.runtime.config import default_runtime_config
from iris.runtime.config.state import RuntimeStateBackend, RuntimeStateConfig
from iris.runtime.delivery.in_memory import InMemoryDeliveryOutbox
from iris.runtime.learning.queue import InMemoryBackgroundJobQueue
from iris.runtime.state.memory_candidates import InMemoryMemoryCandidateReviewStore
from iris.runtime.state.safety_audit import InMemorySafetyAuditJournal
from iris.runtime.state.scheduler_targets import InMemorySchedulerTargetStore
from iris.runtime.wiring.state import wire_runtime_state

if TYPE_CHECKING:
    from pathlib import Path


def test_state_wiring_memory_uses_process_local_delivery_and_scheduler_stores() -> None:
    """Memory backend は process-local outbox と scheduler target を配線する。"""
    stores = wire_runtime_state(default_runtime_config())

    assert isinstance(stores.delivery_outbox, InMemoryDeliveryOutbox)
    assert isinstance(stores.scheduler_target_store, InMemorySchedulerTargetStore)
    assert isinstance(stores.safety_audit_journal, InMemorySafetyAuditJournal)
    assert isinstance(stores.background_job_queue, InMemoryBackgroundJobQueue)
    assert isinstance(stores.memory_candidate_review_store, InMemoryMemoryCandidateReviewStore)


@pytest.mark.anyio
async def test_state_wiring_sqlite_uses_durable_delivery_and_scheduler_stores(
    tmp_path: Path,
) -> None:
    """SQLite backend は durable outbox と scheduler target を配線する。"""
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
    assert isinstance(stores.safety_audit_journal, SQLiteSafetyAuditJournal)
    assert isinstance(stores.background_job_queue, SQLiteBackgroundJobQueue)
    assert isinstance(stores.memory_candidate_review_store, SQLiteMemoryCandidateReviewStore)

    await stores.close()
