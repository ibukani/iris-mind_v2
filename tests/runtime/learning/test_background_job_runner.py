"""BackgroundJobRunner tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import threading

from loguru import logger
import pytest

from iris.runtime.learning.jobs import (
    BackgroundJobId,
    BackgroundJobKind,
    BackgroundJobRecord,
    BackgroundJobResourceProfile,
    BackgroundJobStatus,
    DeferredLearningJobPayload,
)
from iris.runtime.learning.policy import BackgroundJobKindPolicy, BackgroundJobQueuePolicy
from iris.runtime.learning.queue import InMemoryBackgroundJobQueue
from iris.runtime.learning.runner import BackgroundJobRunner, BackgroundJobRunnerRuntimeHooks

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
    runner = BackgroundJobRunner(
        queue, (worker,), runtime_hooks=BackgroundJobRunnerRuntimeHooks(now=lambda: job.not_before)
    )
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
        runtime_hooks=BackgroundJobRunnerRuntimeHooks(now=lambda: first.not_before),
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
    await BackgroundJobRunner(
        queue, (), runtime_hooks=BackgroundJobRunnerRuntimeHooks(now=lambda: job.not_before)
    ).run_once()
    assert (await queue.get(job.job_id)).status is BackgroundJobStatus.FAILED_PERMANENT


class _SideEffectWorker:
    kind = BackgroundJobKind.REFLECTION

    def __init__(self) -> None:
        self.side_effects: list[BackgroundJobId] = []

    def run(self, job: BackgroundJobRecord) -> None:
        """Soft timeout test 用に副作用を記録する。"""
        self.side_effects.append(job.job_id)


async def test_worker_soft_timeout_does_not_retry_after_side_effect() -> None:
    """同期 worker の soft timeout 超過は retryable failure にしない。"""
    queue = InMemoryBackgroundJobQueue()
    job = await queue.enqueue(_job("timeout"))
    worker = _SideEffectWorker()
    monotonic_values = iter((0.0, 2.0))
    runner = BackgroundJobRunner(
        queue,
        (worker,),
        queue_policy=BackgroundJobQueuePolicy(
            default_policy=BackgroundJobKindPolicy(timeout_seconds=1.0)
        ),
        runtime_hooks=BackgroundJobRunnerRuntimeHooks(
            now=lambda: job.not_before,
            monotonic_seconds=lambda: next(monotonic_values),
        ),
    )

    assert await runner.run_once() == 1

    stored = await queue.get(job.job_id)
    assert worker.side_effects == [job.job_id]
    assert stored.status is BackgroundJobStatus.SUCCEEDED


async def test_worker_failure_uses_exponential_retry_backoff() -> None:
    """Worker 失敗時は attempts に応じた指数 backoff を使う。"""
    queue = InMemoryBackgroundJobQueue()
    job = await queue.enqueue(_job("backoff"))
    runner = BackgroundJobRunner(
        queue,
        (_Worker(fail=True),),
        queue_policy=BackgroundJobQueuePolicy(
            default_policy=BackgroundJobKindPolicy(
                retry_backoff_base_seconds=5.0,
                retry_backoff_max_seconds=5.0,
            )
        ),
        runtime_hooks=BackgroundJobRunnerRuntimeHooks(now=lambda: job.not_before),
    )

    assert await runner.run_once() == 1

    stored = await queue.get(job.job_id)
    assert stored.not_before == job.not_before.replace(second=5)


async def test_run_once_exposes_latest_queue_metrics() -> None:
    """Worker loop が収集した queue metrics を diagnostics 用に保持する。"""
    queue = InMemoryBackgroundJobQueue()
    job = await queue.enqueue(_job("metrics"))
    runner = BackgroundJobRunner(
        queue,
        (_Worker(),),
        runtime_hooks=BackgroundJobRunnerRuntimeHooks(now=lambda: job.not_before),
    )

    assert await runner.run_once() == 1

    metrics = runner.latest_metrics
    assert metrics is not None
    assert metrics.succeeded == 1
    assert metrics.queue_depth == 0


class _LeaseInspectingWorker:
    kind = BackgroundJobKind.REFLECTION

    def __init__(self) -> None:
        self.leased_until: datetime | None = None

    def run(self, job: BackgroundJobRecord) -> None:
        self.leased_until = job.leased_until


async def test_runner_lease_duration_covers_kind_timeout() -> None:
    """Runner は kind timeout より短い lease を発行しない。"""
    queue = InMemoryBackgroundJobQueue()
    job = await queue.enqueue(_job("lease-timeout"))
    worker = _LeaseInspectingWorker()
    runner = BackgroundJobRunner(
        queue,
        (worker,),
        lease_seconds=30.0,
        queue_policy=BackgroundJobQueuePolicy(
            default_policy=BackgroundJobKindPolicy(timeout_seconds=60.0)
        ),
        runtime_hooks=BackgroundJobRunnerRuntimeHooks(now=lambda: job.not_before),
    )

    assert await runner.run_once() == 1

    assert worker.leased_until == job.not_before + timedelta(seconds=60)


async def test_runner_does_not_run_idle_only_job_when_not_idle() -> None:
    """Runner は idle_only job を idle 判定なしで実行しない。"""
    queue = InMemoryBackgroundJobQueue()
    job = await queue.enqueue(
        _job("idle-runner").model_copy(
            update={"resource_profile": BackgroundJobResourceProfile(idle_only=True)}
        )
    )
    worker = _Worker()
    runner = BackgroundJobRunner(
        queue,
        (worker,),
        runtime_hooks=BackgroundJobRunnerRuntimeHooks(
            now=lambda: job.not_before,
            idle_available=lambda: False,
        ),
    )

    assert await runner.run_once() == 0

    assert worker.calls == []
    assert (await queue.get(job.job_id)).status is BackgroundJobStatus.PENDING
