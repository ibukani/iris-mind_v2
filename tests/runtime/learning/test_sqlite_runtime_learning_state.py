"""SQLite durable runtime learning state integration tests。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from iris.adapters.persistence.sqlite.stores.background_jobs import SQLiteBackgroundJobQueue
from iris.adapters.persistence.sqlite.stores.memory import SQLiteMemoryStore
from iris.adapters.persistence.sqlite.stores.memory_candidate_reviews import (
    SQLiteMemoryCandidateReviewStore,
)
from iris.contracts.memory import MemoryId, MemoryKind, MemoryRecord
from iris.contracts.memory_candidates import (
    MemoryCandidate,
    MemoryCandidateSensitivity,
    MemoryCandidateSource,
    MemoryRetentionPolicy,
)
from iris.contracts.review_candidates import ReviewCandidateStatus, ReviewDecisionRequest
from iris.core.ids import ActorId, ObservationId, SpaceId
from iris.runtime.learning.jobs import (
    BackgroundJobId,
    BackgroundJobKind,
    BackgroundJobRecord,
    BackgroundJobStatus,
    DeferredLearningJobPayload,
)
from iris.runtime.learning.review_promotion import ApprovedMemoryCandidatePromoter
from iris.runtime.learning.review_service import MemoryCandidateReviewService
from iris.runtime.learning.runner import BackgroundJobRunner
from iris.runtime.state.memory_candidates import (
    MemoryCandidateReviewId,
    MemoryCandidateReviewRecord,
    MemoryCandidateReviewStatus,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.anyio

_NOW = datetime(2026, 7, 1, tzinfo=UTC)
_REVIEWED_AT = datetime(2026, 7, 1, 1, tzinfo=UTC)
_PROMOTED_AT = datetime(2026, 7, 1, 2, tzinfo=UTC)


class _Worker:
    """SQLite queue integration test worker。"""

    kind = BackgroundJobKind.REFLECTION

    def __init__(self) -> None:
        """Call 記録を初期化する。"""
        self.calls: list[BackgroundJobId] = []

    def run(self, job: BackgroundJobRecord) -> None:
        """処理済み job_id を記録する。"""
        self.calls.append(job.job_id)


async def test_reopened_sqlite_background_job_queue_runs_with_runner(
    tmp_path: Path,
) -> None:
    """Reopen 後の SQLite queue job を BackgroundJobRunner が処理できる。"""
    db_path = tmp_path / "state.sqlite3"
    queue = SQLiteBackgroundJobQueue(db_path)
    job = await queue.enqueue(_job("reopened"))
    queue.close()

    reopened = SQLiteBackgroundJobQueue(db_path)
    worker = _Worker()
    runner = BackgroundJobRunner(reopened, (worker,), now=lambda: _NOW)

    assert await runner.run_once() == 1
    assert worker.calls == [job.job_id]
    assert (await reopened.get(job.job_id)).status is BackgroundJobStatus.SUCCEEDED
    reopened.close()

    verified = SQLiteBackgroundJobQueue(db_path)
    try:
        assert (await verified.get(job.job_id)).status is BackgroundJobStatus.SUCCEEDED
    finally:
        verified.close()


async def test_reopened_sqlite_review_service_and_promoter_preserve_lifecycle(
    tmp_path: Path,
) -> None:
    """SQLite review store は approve/promote lifecycle を再起動後も保持する。"""
    db_path = tmp_path / "state.sqlite3"
    review_store = SQLiteMemoryCandidateReviewStore(db_path)
    memory_store = SQLiteMemoryStore(db_path)
    record = await review_store.add(_record("candidate-1"))

    service = MemoryCandidateReviewService(review_store, now=lambda: _REVIEWED_AT)
    approved = await service.approve(
        record.candidate_id,
        ReviewDecisionRequest(reviewed_by="operator", reason="stable preference"),
    )
    assert approved.candidate.status is ReviewCandidateStatus.APPROVED
    review_store.close()
    memory_store.close()

    reopened_review_store = SQLiteMemoryCandidateReviewStore(db_path)
    reopened_memory_store = SQLiteMemoryStore(db_path)
    promoter = ApprovedMemoryCandidatePromoter(
        reopened_review_store,
        reopened_memory_store,
        now=lambda: _PROMOTED_AT,
    )
    result = await promoter.promote(record.candidate_id)

    assert result.promoted is True
    assert result.memory is not None
    assert result.record.promoted_memory_id == str(result.memory.id)
    assert reopened_memory_store.get(result.memory.id) == result.memory
    reopened_review_store.close()
    reopened_memory_store.close()

    await _assert_promoted_state_persisted(
        db_path,
        candidate_id=record.candidate_id,
        promoted_memory_id=str(result.memory.id),
        expected_memory=result.memory,
    )


def _job(key: str) -> BackgroundJobRecord:
    return BackgroundJobRecord(
        job_id=BackgroundJobId(f"job-{key}"),
        kind=BackgroundJobKind.REFLECTION,
        payload=DeferredLearningJobPayload(reason="test"),
        not_before=_NOW,
        idempotency_key=key,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _record(candidate_id: str) -> MemoryCandidateReviewRecord:
    candidate = MemoryCandidate(
        text="ユーザーは短い返答を好む。",
        kind=MemoryKind.PREFERENCE,
        salience=0.6,
        confidence=0.7,
        source=MemoryCandidateSource.IMPLICIT_CONVERSATION,
        reason="implicit style preference",
        retention_policy=MemoryRetentionPolicy.REVIEW_REQUIRED,
        sensitivity=MemoryCandidateSensitivity.NORMAL,
        review_required=True,
        actor_id=ActorId("actor-1"),
        space_id=SpaceId("space-1"),
        source_observation_id=ObservationId("obs-1"),
    )
    return MemoryCandidateReviewRecord(
        candidate_id=MemoryCandidateReviewId(candidate_id),
        candidate=candidate,
        created_at=_NOW,
        updated_at=_NOW,
        idempotency_key=f"review:{candidate_id}",
        actor_id=ActorId("actor-1"),
        space_id=SpaceId("space-1"),
        source_observation_id=ObservationId("obs-1"),
    )


async def _assert_promoted_state_persisted(
    db_path: Path,
    *,
    candidate_id: MemoryCandidateReviewId,
    promoted_memory_id: str,
    expected_memory: MemoryRecord,
) -> None:
    verified_record, stored_memory = await _load_promoted_state(
        db_path,
        candidate_id=candidate_id,
        promoted_memory_id=promoted_memory_id,
    )

    assert verified_record.status is MemoryCandidateReviewStatus.APPROVED
    assert verified_record.reviewed_by == "operator"
    assert verified_record.review_reason == "stable preference"
    assert verified_record.promoted_memory_id == promoted_memory_id
    assert stored_memory == expected_memory


async def _load_promoted_state(
    db_path: Path,
    *,
    candidate_id: MemoryCandidateReviewId,
    promoted_memory_id: str,
) -> tuple[MemoryCandidateReviewRecord, MemoryRecord | None]:
    verified_review_store = SQLiteMemoryCandidateReviewStore(db_path)
    verified_memory_store = SQLiteMemoryStore(db_path)
    try:
        verified_record = await verified_review_store.get(candidate_id)
        stored_memory = verified_memory_store.get(MemoryId(promoted_memory_id))
    finally:
        verified_review_store.close()
        verified_memory_store.close()
    assert verified_record is not None
    return verified_record, stored_memory
