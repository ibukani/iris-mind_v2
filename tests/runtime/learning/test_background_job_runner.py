"""BackgroundJobRunner tests."""

from __future__ import annotations

from datetime import UTC, datetime
import threading

from loguru import logger
import pytest

from iris.runtime.learning.jobs import (
    BackgroundJobId,
    BackgroundJobKind,
    BackgroundJobRecord,
    BackgroundJobStatus,
    DeferredLearningJobPayload,
)
from iris.runtime.learning.queue import InMemoryBackgroundJobQueue
from iris.runtime.learning.runner import BackgroundJobRunner

pytestmark = pytest.mark.anyio


class _Worker:
    kind = BackgroundJobKind.REFLECTION

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[BackgroundJobId] = []
        self.thread_ids: list[int] = []
        self._fail = fail

    def run(self, job: BackgroundJobRecord) -> None:
        self.calls.append(job.job_id)
        self.thread_ids.append(threading.get_ident())
        if self._fail:
            message = "worker failed"
            raise RuntimeError(message)


def _job(key: str) -> BackgroundJobRecord:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return BackgroundJobRecord(
        job_id=BackgroundJobId(f"job-{key}"),
        kind=BackgroundJobKind.REFLECTION,
        payload=DeferredLearningJobPayload(),
        not_before=now,
        idempotency_key=key,
        created_at=now,
        updated_at=now,
    )


async def test_known_worker_succeeds() -> None:
    """登録 worker の正常処理を成功として記録する。"""
    queue = InMemoryBackgroundJobQueue()
    job = await queue.enqueue(_job("ok"))
    worker = _Worker()
    event_loop_thread_id = threading.get_ident()
    runner = BackgroundJobRunner(queue, (worker,), now=lambda: job.not_before)
    assert await runner.run_once() == 1
    assert (await queue.get(job.job_id)).status is BackgroundJobStatus.SUCCEEDED
    assert len(worker.thread_ids) == 1
    assert worker.thread_ids[0] != event_loop_thread_id


async def test_worker_failure_is_retryable_and_does_not_stop_batch() -> None:
    """Worker 障害を再試行可能にし、後続処理を継続する。"""
    queue = InMemoryBackgroundJobQueue()
    first = await queue.enqueue(_job("first"))
    second = await queue.enqueue(_job("second"))
    worker = _Worker(fail=True)
    runner = BackgroundJobRunner(
        queue,
        (worker,),
        retry_backoff_seconds=0.0,
        now=lambda: first.not_before,
    )
    messages: list[str] = []
    sink_id = logger.add(lambda message: messages.append(str(message)))
    try:
        assert await runner.run_once() == 2
    finally:
        logger.remove(sink_id)
    assert worker.calls == [first.job_id, second.job_id]
    assert (await queue.get(first.job_id)).status is BackgroundJobStatus.FAILED_RETRYABLE
    assert any("RuntimeError: worker failed" in message for message in messages)


async def test_missing_worker_is_permanent_failure() -> None:
    """未登録 kind を制御された恒久失敗にする。"""
    queue = InMemoryBackgroundJobQueue()
    job = await queue.enqueue(_job("missing"))
    await BackgroundJobRunner(queue, (), now=lambda: job.not_before).run_once()
    assert (await queue.get(job.job_id)).status is BackgroundJobStatus.FAILED_PERMANENT
