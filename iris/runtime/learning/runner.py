"""バックグラウンドジョブ worker の実行制御。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import time
from typing import TYPE_CHECKING, Protocol, TypedDict, Unpack, runtime_checkable

from loguru import logger

from iris.contracts.model_policy import ModelCallSite
from iris.core.datetime_utils import now_utc
from iris.core.metadata import immutable_metadata
from iris.runtime.inference.models import (
    InferenceLeaseCancellationToken,
    InferenceLeaseDecision,
    InferenceLeaseRequest,
    InferenceLeaseResult,
    InferenceResourceSnapshot,
    InferenceResourceState,
    InferenceSlotKind,
    model_call_site_priority,
)
from iris.runtime.inference.observability import inference_lease_log_fields
from iris.runtime.learning.jobs import BackgroundJobKind
from iris.runtime.learning.policy import BackgroundJobKindPolicy, BackgroundJobQueuePolicy

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from datetime import datetime
    from types import TracebackType

    from iris.runtime.inference.scheduler import LocalInferenceResourceScheduler
    from iris.runtime.learning.jobs import BackgroundJobRecord
    from iris.runtime.learning.policy import BackgroundJobQueueMetrics
    from iris.runtime.learning.queue import BackgroundJobQueue


def _never_idle() -> bool:
    return False


def _monotonic_seconds() -> float:
    return time.monotonic()


@dataclass(frozen=True)
class BackgroundJobRunnerRuntimeHooks:
    """BackgroundJobRunner が参照する runtime 状態 provider。"""

    now: Callable[[], datetime] = now_utc
    idle_available: Callable[[], bool] = _never_idle
    monotonic_seconds: Callable[[], float] = _monotonic_seconds


class BackgroundJobRunnerLegacyOptions(TypedDict, total=False):
    """旧 constructor kwargs の型付き互換境界。"""

    max_jobs_per_run: int
    lease_seconds: float
    queue_policy: BackgroundJobQueuePolicy
    runtime_hooks: BackgroundJobRunnerRuntimeHooks
    inference_scheduler: LocalInferenceResourceScheduler


@dataclass(frozen=True)
class BackgroundJobRunnerOptions:
    """BackgroundJobRunner の batch / lease / policy 設定。"""

    max_jobs_per_run: int = 5
    lease_seconds: float = 30.0
    queue_policy: BackgroundJobQueuePolicy | None = None
    runtime_hooks: BackgroundJobRunnerRuntimeHooks | None = None
    inference_scheduler: LocalInferenceResourceScheduler | None = None


class BackgroundJobWorker(Protocol):
    """単一 kind を処理する worker。"""

    kind: BackgroundJobKind

    def run(self, job: BackgroundJobRecord) -> None:
        """Lease 済みジョブを処理する。"""
        ...


@runtime_checkable
class CancellableBackgroundJobWorker(BackgroundJobWorker, Protocol):
    """#93 preemption を実際に観測できる LLM worker。"""

    def run_with_cancellation(
        self,
        job: BackgroundJobRecord,
        cancellation_token: InferenceLeaseCancellationToken,
    ) -> None:
        """協調キャンセル token を確認しながら Lease 済みジョブを処理する。"""
        ...


class BackgroundJobRunner:
    """due job を lease し、個別障害を隔離して worker へ渡す。"""

    def __init__(
        self,
        queue: BackgroundJobQueue,
        workers: Sequence[BackgroundJobWorker],
        *,
        options: BackgroundJobRunnerOptions | None = None,
        **legacy_options: Unpack[BackgroundJobRunnerLegacyOptions],
    ) -> None:
        """キュー、worker、batch/lease/retry 設定を注入する。"""
        resolved_options = _resolve_runner_options(options, legacy_options)
        self._queue = queue
        self._workers = {worker.kind: worker for worker in workers}
        self._max_jobs_per_run = resolved_options.max_jobs_per_run
        self._lease_seconds = resolved_options.lease_seconds
        self._queue_policy = resolved_options.queue_policy or BackgroundJobQueuePolicy(
            default_policy=BackgroundJobKindPolicy(
                concurrency_limit=resolved_options.max_jobs_per_run
            )
        )
        self._runtime_hooks = resolved_options.runtime_hooks or BackgroundJobRunnerRuntimeHooks()
        self._inference_scheduler = resolved_options.inference_scheduler
        self._latest_metrics: BackgroundJobQueueMetrics | None = None

    @property
    def latest_metrics(self) -> BackgroundJobQueueMetrics | None:
        """最後の run_once() 後に収集した queue metrics snapshot を返す。

        #93 や diagnostics wiring は runner を起動せず queue.collect_metrics() を直接参照できる。
        ここでは worker 実行ループからも直近 snapshot を失わず公開する。

        Returns:
            直近の metrics snapshot。run_once() 未実行時は None。
        """
        return self._latest_metrics

    async def run_once(self) -> int:
        """1 batch を処理し、lease 件数を返す。

        Returns:
            Lease したジョブ数。
        """
        started_at = self._runtime_hooks.now()
        jobs = await self._queue.lease_due(
            started_at,
            self._max_jobs_per_run,
            self._lease_seconds_for_policy(),
            policy=self._queue_policy,
            idle_available=await self._idle_available_for_lease(),
        )
        for job in jobs:
            await self._run_job(job)
        self._latest_metrics = await self._queue.collect_metrics(self._runtime_hooks.now())
        return len(jobs)

    async def _run_job(self, job: BackgroundJobRecord) -> None:
        worker = self._workers.get(job.kind)
        if worker is None:
            await self._queue.mark_permanent_failure(
                job.job_id,
                self._runtime_hooks.now(),
                f"no worker registered for {job.kind}",
            )
            logger.error("background job worker missing: {}", job.kind)
            return
        lease_result = await self._acquire_inference_lease(job, worker)
        logger.debug(
            "background job inference lease decision: {}",
            inference_lease_log_fields(lease_result),
        )
        if not lease_result.acquired:
            await self._apply_inference_lease_rejection(job, lease_result)
            return
        cancellation_token = await self._lease_cancellation_token(lease_result)
        run_result = await self._run_worker_with_failure_isolation(
            worker,
            job,
            cancellation_token,
        )
        lease_still_active = True
        if lease_result.lease_id is not None and self._inference_scheduler is not None:
            lease_still_active = await self._inference_scheduler.release(lease_result.lease_id)
        cancellation_requested = (
            cancellation_token is not None and cancellation_token.cancellation_requested
        )
        if run_result.exception is not None:
            await self._mark_retryable_failure(job, run_result.exception)
        elif cancellation_requested or not lease_still_active:
            await self._defer_lost_inference_lease(job)
        else:
            self._record_soft_timeout(job, run_result.elapsed_seconds)
            await self._queue.mark_succeeded(job.job_id, self._runtime_hooks.now())

    async def _run_worker_with_failure_isolation(
        self,
        worker: BackgroundJobWorker,
        job: BackgroundJobRecord,
        cancellation_token: InferenceLeaseCancellationToken | None,
    ) -> _WorkerRunResult:
        started_at = self._runtime_hooks.monotonic_seconds()
        failure = _CaptureWorkerFailure()
        with failure:
            if cancellation_token is not None and isinstance(
                worker, CancellableBackgroundJobWorker
            ):
                await asyncio.to_thread(
                    worker.run_with_cancellation,
                    job,
                    cancellation_token,
                )
            else:
                await asyncio.to_thread(worker.run, job)
        elapsed_seconds = self._runtime_hooks.monotonic_seconds() - started_at
        return _WorkerRunResult(exception=failure.exception, elapsed_seconds=elapsed_seconds)

    def _record_soft_timeout(self, job: BackgroundJobRecord, elapsed_seconds: float) -> None:
        kind_policy = self._queue_policy.for_kind(job.kind)
        if elapsed_seconds <= kind_policy.timeout_seconds:
            return
        message = (
            "background job exceeded soft timeout: "
            "job_id={} kind={} elapsed_seconds={:.3f} timeout_seconds={:.3f}"
        )
        logger.warning(
            message,
            job.job_id,
            job.kind,
            elapsed_seconds,
            kind_policy.timeout_seconds,
        )

    async def _acquire_inference_lease(
        self,
        job: BackgroundJobRecord,
        worker: BackgroundJobWorker,
    ) -> InferenceLeaseResult:
        scheduler = self._inference_scheduler
        if scheduler is None or not _job_uses_llm(job, self._queue_policy.for_kind(job.kind)):
            return _synthetic_acquired_lease(job)
        descriptor = job.resource_profile.model_call_descriptor
        call_site = (
            descriptor.call_site if descriptor is not None else _call_site_for_job_kind(job.kind)
        )
        worker_preemptible = isinstance(worker, CancellableBackgroundJobWorker)
        request = InferenceLeaseRequest(
            slot_kind=InferenceSlotKind.BACKGROUND_LLM,
            priority=model_call_site_priority(call_site),
            call_site=call_site,
            model_slot=descriptor.model_slot if descriptor is not None else None,
            model_name=descriptor.model_name if descriptor is not None else None,
            preemptible=worker_preemptible,
            metadata=immutable_metadata(
                {
                    "background_job_kind": job.kind.value,
                    "call_site": call_site.value,
                }
            ),
        )
        lease_result = await scheduler.acquire(request)
        if lease_result.acquired and not worker_preemptible:
            if lease_result.lease_id is not None:
                await scheduler.release(lease_result.lease_id)
            return InferenceLeaseResult(
                decision=InferenceLeaseDecision.DEFER,
                reason="background LLM worker lacks cooperative cancellation",
                request=request,
                snapshot=await scheduler.snapshot(),
            )
        return lease_result

    async def _lease_cancellation_token(
        self,
        lease_result: InferenceLeaseResult,
    ) -> InferenceLeaseCancellationToken | None:
        if self._inference_scheduler is None or lease_result.lease_id is None:
            return None
        return await self._inference_scheduler.cancellation_token(lease_result.lease_id)

    async def _apply_inference_lease_rejection(
        self,
        job: BackgroundJobRecord,
        lease_result: InferenceLeaseResult,
    ) -> None:
        reason = f"inference resource {lease_result.decision.value}: {lease_result.reason}"
        if lease_result.decision is InferenceLeaseDecision.DEFER:
            await self._defer_leased_job(job, reason)
            logger.info("background job deferred by inference scheduler: {}", job.job_id)
            return
        await self._queue.mark_cancelled(job.job_id, self._runtime_hooks.now(), reason)
        logger.info("background job cancelled by inference scheduler: {}", job.job_id)

    async def _defer_lost_inference_lease(self, job: BackgroundJobRecord) -> None:
        reason = "inference resource defer: active lease disappeared before completion"
        await self._defer_leased_job(job, reason)
        logger.info("background job deferred after lost inference lease: {}", job.job_id)

    async def _defer_leased_job(self, job: BackgroundJobRecord, reason: str) -> None:
        defer_seconds = self._queue_policy.for_kind(job.kind).defer_seconds_when_saturated
        await self._queue.defer_leased(
            job.job_id,
            self._runtime_hooks.now() + timedelta(seconds=defer_seconds),
            reason,
        )

    async def _mark_retryable_failure(self, job: BackgroundJobRecord, exc: Exception) -> None:
        failed_at = self._runtime_hooks.now()
        retry_after = failed_at + timedelta(seconds=self._retry_delay_seconds(job))
        await self._queue.mark_retryable_failure(
            job.job_id,
            failed_at,
            str(exc),
            retry_after,
        )
        logger.opt(exception=exc).error(
            "background job failed: {}",
            job.job_id,
        )

    async def _idle_available_for_lease(self) -> bool:
        if self._runtime_hooks.idle_available():
            return True
        if self._inference_scheduler is None:
            return False
        snapshot = await self._inference_scheduler.snapshot()
        return snapshot.state is InferenceResourceState.IDLE

    def _retry_delay_seconds(self, job: BackgroundJobRecord) -> float:
        return self._queue_policy.for_kind(job.kind).retry_delay_seconds(job.attempts)

    def _lease_seconds_for_policy(self) -> float:
        return max(self._lease_seconds, self._queue_policy.max_timeout_seconds())


def _resolve_runner_options(
    options: BackgroundJobRunnerOptions | None,
    legacy_options: BackgroundJobRunnerLegacyOptions,
) -> BackgroundJobRunnerOptions:
    if not legacy_options:
        return options or BackgroundJobRunnerOptions()
    if options is not None:
        message = "BackgroundJobRunner options cannot be combined with legacy kwargs"
        raise TypeError(message)
    return BackgroundJobRunnerOptions(
        max_jobs_per_run=legacy_options.get("max_jobs_per_run", 5),
        lease_seconds=legacy_options.get("lease_seconds", 30.0),
        queue_policy=legacy_options.get("queue_policy"),
        runtime_hooks=legacy_options.get("runtime_hooks"),
        inference_scheduler=legacy_options.get("inference_scheduler"),
    )


@dataclass(frozen=True)
class _WorkerRunResult:
    """worker 実行結果を queue 状態更新前に保持する。"""

    exception: Exception | None
    elapsed_seconds: float


class _CaptureWorkerFailure:
    """worker 例外を捕捉し、batch 継続を可能にする。"""

    def __init__(self) -> None:
        self.exception: Exception | None = None

    def __enter__(self) -> None:
        return None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        _ = exc_type, traceback
        if exc is None or not isinstance(exc, Exception):
            return False
        self.exception = exc
        return True


def _job_uses_llm(job: BackgroundJobRecord, kind_policy: BackgroundJobKindPolicy) -> bool:
    return job.resource_profile.uses_llm or kind_policy.uses_llm


def _call_site_for_job_kind(kind: BackgroundJobKind) -> ModelCallSite:
    if kind is BackgroundJobKind.MEMORY_EXTRACTION:
        return ModelCallSite.MEMORY_EXTRACTION
    if kind is BackgroundJobKind.REFLECTION:
        return ModelCallSite.REFLECTION
    if kind is BackgroundJobKind.RELATIONSHIP_UPDATE:
        return ModelCallSite.RELATIONSHIP_UPDATE
    return ModelCallSite.RUNTIME_LEARNING_HOOK


def _synthetic_acquired_lease(job: BackgroundJobRecord) -> InferenceLeaseResult:
    request = InferenceLeaseRequest(
        slot_kind=InferenceSlotKind.BACKGROUND_LLM,
        priority=model_call_site_priority(_call_site_for_job_kind(job.kind)),
        call_site=_call_site_for_job_kind(job.kind),
        metadata=immutable_metadata({"background_job_kind": job.kind.value}),
    )
    return InferenceLeaseResult(
        decision=InferenceLeaseDecision.ACQUIRED,
        reason="no inference resource lease required",
        request=request,
        snapshot=InferenceResourceSnapshot(state=InferenceResourceState.IDLE),
        lease_id=None,
    )
