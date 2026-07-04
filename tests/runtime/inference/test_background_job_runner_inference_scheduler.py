"""BackgroundJobRunner と inference scheduler の統合テスト。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from iris.contracts.model_policy import ModelCallSite
from iris.runtime.inference.models import (
    InferenceLeaseRequest,
    InferenceResourceState,
    InferenceSlotKind,
    InferenceWorkPriority,
)
from iris.runtime.inference.policy import LocalInferenceResourcePolicy
from iris.runtime.inference.scheduler import LocalInferenceResourceScheduler
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

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


class _Worker:
    kind = BackgroundJobKind.REFLECTION

    def __init__(self) -> None:
        self.calls: list[BackgroundJobId] = []

    def run(self, job: BackgroundJobRecord) -> None:
        self.calls.append(job.job_id)


def _job(key: str, *, uses_llm: bool) -> BackgroundJobRecord:
    return BackgroundJobRecord(
        job_id=BackgroundJobId(f"job-{key}"),
        kind=BackgroundJobKind.REFLECTION,
        payload=DeferredLearningJobPayload(),
        not_before=_NOW,
        resource_profile=BackgroundJobResourceProfile(uses_llm=uses_llm),
        idempotency_key=key,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _queue_policy() -> BackgroundJobQueuePolicy:
    return BackgroundJobQueuePolicy(
        default_policy=BackgroundJobKindPolicy(
            uses_llm=True,
            defer_seconds_when_saturated=30.0,
        )
    )


async def test_llm_job_is_deferred_when_large_slot_is_busy() -> None:
    """LLM-using background job は resource busy 時に worker を呼ばず defer される。"""
    queue = InMemoryBackgroundJobQueue()
    job = await queue.enqueue(_job("busy", uses_llm=True))
    scheduler = LocalInferenceResourceScheduler(policy=LocalInferenceResourcePolicy(enabled=True))
    await scheduler.set_state(InferenceResourceState.BUSY)
    worker = _Worker()
    runner = BackgroundJobRunner(
        queue,
        (worker,),
        queue_policy=_queue_policy(),
        runtime_hooks=BackgroundJobRunnerRuntimeHooks(now=lambda: _NOW),
        inference_scheduler=scheduler,
    )

    assert await runner.run_once() == 1

    stored = await queue.get(job.job_id)
    assert worker.calls == []
    assert stored.status is BackgroundJobStatus.PENDING
    assert stored.not_before == _NOW.replace(second=30)
    assert stored.defer_reason is not None
    assert "inference resource defer" in stored.defer_reason


async def test_llm_job_is_cancelled_when_resource_unavailable() -> None:
    """Unavailable 時の background LLM job は policy どおり恒久失敗にできる。"""
    queue = InMemoryBackgroundJobQueue()
    job = await queue.enqueue(_job("unavailable", uses_llm=True))
    scheduler = LocalInferenceResourceScheduler(policy=LocalInferenceResourcePolicy(enabled=True))
    await scheduler.set_state(InferenceResourceState.UNAVAILABLE)
    worker = _Worker()
    runner = BackgroundJobRunner(
        queue,
        (worker,),
        queue_policy=_queue_policy(),
        runtime_hooks=BackgroundJobRunnerRuntimeHooks(now=lambda: _NOW),
        inference_scheduler=scheduler,
    )

    assert await runner.run_once() == 1

    stored = await queue.get(job.job_id)
    assert worker.calls == []
    assert stored.status is BackgroundJobStatus.FAILED_PERMANENT
    assert stored.last_error is not None
    assert "inference resource cancel" in stored.last_error


async def test_non_llm_job_runs_when_resource_unavailable() -> None:
    """LLM を使わない job は scheduler unavailable に影響されない。"""
    queue = InMemoryBackgroundJobQueue()
    job = await queue.enqueue(_job("non-llm", uses_llm=False))
    scheduler = LocalInferenceResourceScheduler(policy=LocalInferenceResourcePolicy(enabled=True))
    await scheduler.set_state(InferenceResourceState.UNAVAILABLE)
    worker = _Worker()
    runner = BackgroundJobRunner(
        queue,
        (worker,),
        queue_policy=BackgroundJobQueuePolicy(
            default_policy=BackgroundJobKindPolicy(uses_llm=False)
        ),
        runtime_hooks=BackgroundJobRunnerRuntimeHooks(now=lambda: _NOW),
        inference_scheduler=scheduler,
    )

    assert await runner.run_once() == 1

    stored = await queue.get(job.job_id)
    assert worker.calls == [job.job_id]
    assert stored.status is BackgroundJobStatus.SUCCEEDED


class _PreemptingWorker:
    kind = BackgroundJobKind.REFLECTION

    def __init__(
        self,
        *,
        scheduler: LocalInferenceResourceScheduler,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._scheduler = scheduler
        self._loop = loop
        self.calls: list[BackgroundJobId] = []

    def run(self, job: BackgroundJobRecord) -> None:
        self.calls.append(job.job_id)
        future = asyncio.run_coroutine_threadsafe(
            self._scheduler.acquire(
                InferenceLeaseRequest(
                    slot_kind=InferenceSlotKind.LARGE_LLM,
                    priority=InferenceWorkPriority.USER_FACING_RESPONSE,
                    call_site=ModelCallSite.USER_RESPONSE_HOT_PATH,
                )
            ),
            self._loop,
        )
        result = future.result(timeout=1.0)
        assert result.acquired
        assert result.lease_id is not None
        release = asyncio.run_coroutine_threadsafe(
            self._scheduler.release(result.lease_id),
            self._loop,
        )
        assert release.result(timeout=1.0)


async def test_preempted_background_job_is_deferred_after_worker_returns() -> None:
    """user-facing lease に preempt された background job は成功扱いにしない。"""
    queue = InMemoryBackgroundJobQueue()
    job = await queue.enqueue(_job("preempted", uses_llm=True))
    scheduler = LocalInferenceResourceScheduler(policy=LocalInferenceResourcePolicy(enabled=True))
    worker = _PreemptingWorker(scheduler=scheduler, loop=asyncio.get_running_loop())
    runner = BackgroundJobRunner(
        queue,
        (worker,),
        queue_policy=_queue_policy(),
        runtime_hooks=BackgroundJobRunnerRuntimeHooks(now=lambda: _NOW),
        inference_scheduler=scheduler,
    )

    assert await runner.run_once() == 1

    stored = await queue.get(job.job_id)
    assert worker.calls == [job.job_id]
    assert stored.status is BackgroundJobStatus.PENDING
    assert stored.not_before == _NOW.replace(second=30)
    assert stored.defer_reason == "inference resource defer: low priority lease was preempted"
