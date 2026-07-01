"""バックグラウンドジョブキュー境界とインメモリ実装。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Protocol

from iris.runtime.learning.jobs import BackgroundJobStatus

if TYPE_CHECKING:
    from datetime import datetime

    from iris.runtime.learning.jobs import BackgroundJobId, BackgroundJobRecord


class BackgroundJobQueueError(RuntimeError):
    """バックグラウンドジョブ遷移エラー。"""


class BackgroundJobQueue(Protocol):
    """BackgroundJobRunner が利用するジョブキュー境界。"""

    async def enqueue(self, job: BackgroundJobRecord) -> BackgroundJobRecord:
        """ジョブを冪等に登録する。"""
        ...

    async def lease_due(
        self,
        now: datetime,
        max_items: int,
        lease_seconds: float,
    ) -> tuple[BackgroundJobRecord, ...]:
        """期限到来済みジョブを lease する。"""
        ...

    async def mark_succeeded(self, job_id: BackgroundJobId, finished_at: datetime) -> None:
        """Lease 中ジョブを成功完了にする。"""
        ...

    async def mark_retryable_failure(
        self,
        job_id: BackgroundJobId,
        failed_at: datetime,
        reason: str,
        retry_after: datetime,
    ) -> None:
        """再試行可能または恒久失敗として記録する。"""
        ...

    async def mark_permanent_failure(
        self, job_id: BackgroundJobId, failed_at: datetime, reason: str
    ) -> None:
        """ジョブを恒久失敗にする。"""
        ...

    async def get(self, job_id: BackgroundJobId) -> BackgroundJobRecord:
        """指定 ID のジョブを返す。"""
        ...


class InMemoryBackgroundJobQueue:
    """idempotency key と lease を持つプロセス内キュー。"""

    def __init__(self) -> None:
        """空のジョブ集合と排他 lock で初期化する。"""
        self._jobs: dict[BackgroundJobId, BackgroundJobRecord] = {}
        self._idempotency_keys: dict[str, BackgroundJobId] = {}
        self._lock = asyncio.Lock()

    async def enqueue(self, job: BackgroundJobRecord) -> BackgroundJobRecord:
        """ジョブを冪等に登録する。

        Returns:
            新規または同じ idempotency key の既存ジョブ。
        """
        async with self._lock:
            existing_id = self._idempotency_keys.get(job.idempotency_key)
            if existing_id is not None:
                return self._jobs[existing_id]
            self._jobs[job.job_id] = job
            self._idempotency_keys[job.idempotency_key] = job.job_id
            return job

    async def lease_due(
        self,
        now: datetime,
        max_items: int,
        lease_seconds: float,
    ) -> tuple[BackgroundJobRecord, ...]:
        """期限到来済みジョブを決定的順序で lease する。

        Returns:
            Lease したジョブ。
        """
        async with self._lock:
            due = sorted(self._jobs.values(), key=_job_order)
            leased: list[BackgroundJobRecord] = []
            for job in due:
                lease_expired = job.status is BackgroundJobStatus.LEASED and (
                    job.leased_until is not None and job.leased_until <= now
                )
                ready = job.status in {
                    BackgroundJobStatus.PENDING,
                    BackgroundJobStatus.FAILED_RETRYABLE,
                }
                if (not ready and not lease_expired) or job.not_before > now:
                    continue
                updated = replace_job(
                    job,
                    JobUpdate(
                        status=BackgroundJobStatus.LEASED,
                        leased_until=now + timedelta(seconds=lease_seconds),
                        updated_at=now,
                    ),
                )
                self._jobs[job.job_id] = updated
                leased.append(updated)
                if len(leased) >= max_items:
                    break
            return tuple(leased)

    async def mark_succeeded(self, job_id: BackgroundJobId, finished_at: datetime) -> None:
        """Lease 中ジョブを成功完了にする。"""
        await self._update_terminal(job_id, BackgroundJobStatus.SUCCEEDED, finished_at, None)

    async def mark_retryable_failure(
        self,
        job_id: BackgroundJobId,
        failed_at: datetime,
        reason: str,
        retry_after: datetime,
    ) -> None:
        """試行回数を増やし、再試行または恒久失敗へ遷移する。"""
        async with self._lock:
            job = self._require(job_id)
            attempts = job.attempts + 1
            status = retry_failure_status(attempts=attempts, max_attempts=job.max_attempts)
            self._jobs[job_id] = replace_job(
                job,
                JobUpdate(
                    status=status,
                    attempts=attempts,
                    not_before=retry_after,
                    leased_until=None,
                    updated_at=failed_at,
                    last_error=reason,
                ),
            )

    async def mark_permanent_failure(
        self, job_id: BackgroundJobId, failed_at: datetime, reason: str
    ) -> None:
        """ジョブを恒久失敗にする。"""
        await self._update_terminal(job_id, BackgroundJobStatus.FAILED_PERMANENT, failed_at, reason)

    async def get(self, job_id: BackgroundJobId) -> BackgroundJobRecord:
        """ジョブを取得する。

        Returns:
            指定 ID のジョブ。
        """
        async with self._lock:
            return self._require(job_id)

    def _require(self, job_id: BackgroundJobId) -> BackgroundJobRecord:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            message = f"unknown background job: {job_id}"
            raise BackgroundJobQueueError(message) from exc

    async def _update_terminal(
        self,
        job_id: BackgroundJobId,
        status: BackgroundJobStatus,
        updated_at: datetime,
        error: str | None,
    ) -> None:
        async with self._lock:
            job = self._require(job_id)
            self._jobs[job_id] = replace_job(
                job,
                JobUpdate(
                    status=status,
                    leased_until=None,
                    updated_at=updated_at,
                    last_error=error,
                ),
            )


def retry_failure_status(*, attempts: int, max_attempts: int) -> BackgroundJobStatus:
    """試行回数に応じた失敗状態を返す。

    Returns:
        再試行可能または恒久失敗の状態。
    """
    if attempts >= max_attempts:
        return BackgroundJobStatus.FAILED_PERMANENT
    return BackgroundJobStatus.FAILED_RETRYABLE


def _job_order(job: BackgroundJobRecord) -> tuple[datetime, datetime, str]:
    return job.not_before, job.created_at, str(job.job_id)


@dataclass(frozen=True)
class JobUpdate:
    """BackgroundJobRecord の状態更新値。"""

    status: BackgroundJobStatus
    updated_at: datetime
    attempts: int | None = None
    not_before: datetime | None = None
    leased_until: datetime | None = None
    last_error: str | None = None


def replace_job(job: BackgroundJobRecord, update: JobUpdate) -> BackgroundJobRecord:
    """型を失わずジョブ状態を再構築する。

    Returns:
        更新済みジョブ。
    """
    return type(job)(
        job_id=job.job_id,
        kind=job.kind,
        payload=job.payload,
        status=update.status,
        attempts=job.attempts if update.attempts is None else update.attempts,
        max_attempts=job.max_attempts,
        not_before=job.not_before if update.not_before is None else update.not_before,
        leased_until=update.leased_until,
        idempotency_key=job.idempotency_key,
        created_at=job.created_at,
        updated_at=update.updated_at,
        last_error=update.last_error,
    )
