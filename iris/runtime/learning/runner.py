"""バックグラウンドジョブ worker の実行制御。"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING, Protocol

from loguru import logger

from iris.core.datetime_utils import now_utc

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
        retry_backoff_seconds: float = 30.0,
        now: Callable[[], datetime] = now_utc,
    ) -> None:
        """キュー、worker、batch/lease/retry 設定を注入する。"""
        self._queue = queue
        self._workers = {worker.kind: worker for worker in workers}
        self._max_jobs_per_run = max_jobs_per_run
        self._lease_seconds = lease_seconds
        self._retry_backoff_seconds = retry_backoff_seconds
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
        )
        for job in jobs:
            worker = self._workers.get(job.kind)
            if worker is None:
                await self._queue.mark_permanent_failure(
                    job.job_id,
                    self._now(),
                    f"no worker registered for {job.kind}",
                )
                logger.error("background job worker missing: {}", job.kind)
                continue
            failure = _CaptureWorkerFailure()
            with failure:
                await asyncio.to_thread(worker.run, job)
            if failure.exception is not None:
                failed_at = self._now()
                await self._queue.mark_retryable_failure(
                    job.job_id,
                    failed_at,
                    str(failure.exception),
                    failed_at + timedelta(seconds=self._retry_backoff_seconds),
                )
                logger.opt(exception=failure.exception).error(
                    "background job failed: {}",
                    job.job_id,
                )
                continue
            await self._queue.mark_succeeded(job.job_id, self._now())
        return len(jobs)


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
