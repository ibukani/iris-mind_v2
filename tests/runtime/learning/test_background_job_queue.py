"""InMemoryBackgroundJobQueue tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from iris.runtime.learning.jobs import (
    BackgroundJobId,
    BackgroundJobKind,
    BackgroundJobRecord,
    BackgroundJobStatus,
    DeferredLearningJobPayload,
)
from iris.runtime.learning.queue import InMemoryBackgroundJobQueue

pytestmark = pytest.mark.anyio


def _job(*, key: str = "key-1", max_attempts: int = 2) -> BackgroundJobRecord:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return BackgroundJobRecord(
        job_id=BackgroundJobId(f"job-{key}"),
        kind=BackgroundJobKind.REFLECTION,
        payload=DeferredLearningJobPayload(reason="test"),
        max_attempts=max_attempts,
        not_before=now,
        idempotency_key=key,
        created_at=now,
        updated_at=now,
    )


async def test_enqueue_is_idempotent_and_due_job_leases() -> None:
    """Idempotency key と due lease を保証する。"""
    queue = InMemoryBackgroundJobQueue()
    first = await queue.enqueue(_job())
    duplicate = await queue.enqueue(_job())
    leased = await queue.lease_due(first.not_before, 5, 10.0)
    assert duplicate.job_id == first.job_id
    assert leased[0].status is BackgroundJobStatus.LEASED
    assert await queue.lease_due(first.not_before, 5, 10.0) == ()


async def test_expired_lease_can_be_leased_again() -> None:
    """期限切れ lease を再取得できる。"""
    queue = InMemoryBackgroundJobQueue()
    job = await queue.enqueue(_job())
    await queue.lease_due(job.not_before, 1, 10.0)
    leased_again = await queue.lease_due(job.not_before + timedelta(seconds=10), 1, 10.0)
    assert leased_again[0].job_id == job.job_id


async def test_retryable_failure_becomes_permanent_at_max_attempts() -> None:
    """最大試行回数で恒久失敗へ遷移する。"""
    queue = InMemoryBackgroundJobQueue()
    job = await queue.enqueue(_job(max_attempts=2))
    now = job.not_before
    await queue.lease_due(now, 1, 10.0)
    await queue.mark_retryable_failure(job.job_id, now, "first", now)
    assert (await queue.get(job.job_id)).status is BackgroundJobStatus.FAILED_RETRYABLE
    await queue.lease_due(now, 1, 10.0)
    await queue.mark_retryable_failure(job.job_id, now, "second", now)
    assert (await queue.get(job.job_id)).status is BackgroundJobStatus.FAILED_PERMANENT
    assert await queue.lease_due(now, 1, 10.0) == ()
