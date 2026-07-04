"""バックグラウンドジョブ worker の実行制御。"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING, Protocol

from loguru import logger

from iris.core.datetime_utils import now_utc
from iris.runtime.learning.policy import BackgroundJobKindPolicy, BackgroundJobQueuePolicy

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from datetime import datetime
    from types import TracebackType

    from iris.runtime.learning.jobs import BackgroundJobKind, BackgroundJobRecord
    from iris.runtime.learning.queue import BackgroundJobQueue


class BackgroundJobWorker(Protocol):
    """単一 kind を処理する worker。"""

    kind: BackgroundJobKind

    def run(self, job: BackgroundJobRecord) -> None:
        """Lease 済みジョブを処理する。"""
        ...


class BackgroundJobRunner:
    """due job を lease し、個別障害を隔離して worker へ渡す。"""

    def __init__(
        self,
        queue: BackgroundJobQueue,
        workers: Sequence[BackgroundJobWorker],
        *,
        max_jobs_per_run: int = 5,
        lease_seconds: float = 30.0,
        queue_policy: BackgroundJobQueuePolicy | None = None,
        now: Callable[[], datetime] = now_utc,
    ) -> None:
        """キュー、worker、batch/lease/retry 設定を注入する。"""
        self._queue = queue
        self._workers = {worker.kind: worker for worker in workers}
        self._max_jobs_per_run = max_jobs_per_run
        self._lease_seconds = lease_seconds
        self._queue_policy = queue_policy or BackgroundJobQueuePolicy(
            default_policy=BackgroundJobKindPolicy(concurrency_limit=max_jobs_per_run)
        )
        self._now = now

    async def run_once(self) -> int:
        """1 batch を処理し、lease 件数を返す。

        Returns:
            Lease したジョブ数。
        """
        started_at = self._now()
        jobs = await self._queue.lease_due(
            started_at,
            self._max_jobs_per_run,
            self._lease_seconds,
            policy=self._queue_policy,
        )
        for job in jobs:
            await self._run_job(job)
        await self._queue.collect_metrics(self._now())
        return len(jobs)

    async def _run_job(self, job: BackgroundJobRecord) -> None:
        worker = self._workers.get(job.kind)
        if worker is None:
            await self._queue.mark_permanent_failure(
                job.job_id,
                self._now(),
                f"no worker registered for {job.kind}",
            )
            logger.error("background job worker missing: {}", job.kind)
            return
        failure = _CaptureWorkerFailure()
        with failure:
            await asyncio.wait_for(
                asyncio.to_thread(worker.run, job),
                timeout=self._queue_policy.for_kind(job.kind).timeout_seconds,
            )
        if failure.exception is not None:
            await self._mark_retryable_failure(job, failure.exception)
            return
        await self._queue.mark_succeeded(job.job_id, self._now())

    async def _mark_retryable_failure(self, job: BackgroundJobRecord, exc: Exception) -> None:
        failed_at = self._now()
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

    def _retry_delay_seconds(self, job: BackgroundJobRecord) -> float:
        return self._queue_policy.for_kind(job.kind).retry_delay_seconds(job.attempts)


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
