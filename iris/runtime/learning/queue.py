"""バックグラウンドジョブキュー境界とインメモリ実装。"""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Protocol

from iris.runtime.learning.jobs import BackgroundJobKind, BackgroundJobStatus
from iris.runtime.learning.policy import (
    BackgroundJobBackpressureMode,
    BackgroundJobBackpressureReason,
    BackgroundJobEnqueueDecision,
    BackgroundJobEnqueueResult,
    BackgroundJobKindMetrics,
    BackgroundJobKindPolicy,
    BackgroundJobQueueMetrics,
    BackgroundJobQueuePolicy,
    defer_job_record,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from iris.runtime.learning.jobs import BackgroundJobId, BackgroundJobRecord

_QUEUE_DEPTH_STATUSES = frozenset(
    {
        BackgroundJobStatus.PENDING,
        BackgroundJobStatus.FAILED_RETRYABLE,
    }
)
_TERMINAL_STATUSES = frozenset(
    {
        BackgroundJobStatus.SUCCEEDED,
        BackgroundJobStatus.FAILED_PERMANENT,
        BackgroundJobStatus.CANCELLED,
    }
)

__all__ = (
    "BackgroundJobBackpressureMode",
    "BackgroundJobBackpressureReason",
    "BackgroundJobEnqueueDecision",
    "BackgroundJobEnqueueResult",
    "BackgroundJobKindMetrics",
    "BackgroundJobKindPolicy",
    "BackgroundJobQueue",
    "BackgroundJobQueueError",
    "BackgroundJobQueueMetrics",
    "BackgroundJobQueuePolicy",
    "InMemoryBackgroundJobQueue",
    "JobUpdate",
    "defer_job_record",
    "evaluate_enqueue_backpressure",
    "replace_job",
    "retry_failure_status",
)


class BackgroundJobQueueError(RuntimeError):
    """バックグラウンドジョブ遷移エラー。"""


class BackgroundJobQueue(Protocol):
    """BackgroundJobRunner が利用するジョブキュー境界。"""

    async def enqueue(self, job: BackgroundJobRecord) -> BackgroundJobRecord:
        """ジョブを冪等に登録する。"""
        ...

    async def enqueue_with_policy(
        self,
        job: BackgroundJobRecord,
        *,
        now: datetime,
        policy: BackgroundJobQueuePolicy,
        idle_available: bool = False,
    ) -> BackgroundJobEnqueueResult:
        """Backpressure policy を適用して enqueue する。"""
        ...

    async def lease_due(
        self,
        now: datetime,
        max_items: int,
        lease_seconds: float,
        *,
        policy: BackgroundJobQueuePolicy | None = None,
    ) -> tuple[BackgroundJobRecord, ...]:
        """期限到来済みジョブを lease する。"""
        ...

    async def collect_metrics(self, now: datetime) -> BackgroundJobQueueMetrics:
        """現在の queue metrics snapshot を返す。

        Returns:
            queue metrics snapshot。
        """
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
            新規または同じ idempotency key / job_id の既存ジョブ。
        """
        async with self._lock:
            existing = self._existing_job(job)
            if existing is not None:
                return existing
            self._store_job(job)
            return job

    async def enqueue_with_policy(
        self,
        job: BackgroundJobRecord,
        *,
        now: datetime,
        policy: BackgroundJobQueuePolicy,
        idle_available: bool = False,
    ) -> BackgroundJobEnqueueResult:
        """Backpressure policy を適用して enqueue する。

        Returns:
            enqueue 判定と保存 job。
        """
        async with self._lock:
            existing = self._existing_job(job)
            if existing is not None:
                return BackgroundJobEnqueueResult(
                    decision=BackgroundJobEnqueueDecision.EXISTING,
                    record=existing,
                )
            kind_policy = policy.for_kind(job.kind)
            reason = evaluate_enqueue_backpressure(
                job,
                jobs=self._jobs.values(),
                now=now,
                policy=kind_policy,
                idle_available=idle_available,
            )
            if (
                reason is None
                or kind_policy.backpressure_mode is BackgroundJobBackpressureMode.ACCEPT
            ):
                self._store_job(job)
                return BackgroundJobEnqueueResult(
                    decision=BackgroundJobEnqueueDecision.ACCEPTED,
                    record=job,
                )
            if kind_policy.backpressure_mode is BackgroundJobBackpressureMode.REJECT:
                return BackgroundJobEnqueueResult(
                    decision=BackgroundJobEnqueueDecision.REJECTED,
                    record=None,
                    reason=reason,
                )
            deferred_until = now + timedelta(seconds=kind_policy.defer_seconds_when_saturated)
            deferred = defer_job_record(job, deferred_until=deferred_until, reason=reason)
            self._store_job(deferred)
            return BackgroundJobEnqueueResult(
                decision=BackgroundJobEnqueueDecision.DEFERRED,
                record=deferred,
                reason=reason,
                deferred_until=deferred_until,
            )

    async def lease_due(
        self,
        now: datetime,
        max_items: int,
        lease_seconds: float,
        *,
        policy: BackgroundJobQueuePolicy | None = None,
    ) -> tuple[BackgroundJobRecord, ...]:
        """期限到来済みジョブを決定的順序で lease する。

        Returns:
            Lease したジョブ。
        """
        if max_items <= 0:
            return ()
        async with self._lock:
            due = sorted(self._jobs.values(), key=_job_order)
            leased: list[BackgroundJobRecord] = []
            leased_counts = _leased_counts(self._jobs.values(), now)
            for job in due:
                if not _is_leaseable(job, now):
                    continue
                if policy is not None:
                    kind_policy = policy.for_kind(job.kind)
                    if leased_counts[job.kind] >= kind_policy.concurrency_limit:
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
                leased_counts[job.kind] += 1
                leased.append(updated)
                if len(leased) >= max_items:
                    break
            return tuple(leased)

    async def collect_metrics(self, now: datetime) -> BackgroundJobQueueMetrics:
        """現在の queue metrics snapshot を返す。

        Returns:
            queue metrics snapshot。
        """
        async with self._lock:
            return _metrics_from_jobs(self._jobs.values(), now)

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

    def _existing_job(self, job: BackgroundJobRecord) -> BackgroundJobRecord | None:
        if job.job_id in self._jobs:
            return self._jobs[job.job_id]
        existing_id = self._idempotency_keys.get(job.idempotency_key)
        if existing_id is None:
            return None
        return self._jobs[existing_id]

    def _store_job(self, job: BackgroundJobRecord) -> None:
        self._jobs[job.job_id] = job
        self._idempotency_keys[job.idempotency_key] = job.job_id

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


def evaluate_enqueue_backpressure(
    job: BackgroundJobRecord,
    *,
    jobs: Iterable[BackgroundJobRecord],
    now: datetime,
    policy: BackgroundJobKindPolicy,
    idle_available: bool,
) -> BackgroundJobBackpressureReason | None:
    """Enqueue 時に適用すべき backpressure reason を返す。

    Returns:
        backpressure reason。制限なしの場合は None。
    """
    materialized_jobs = tuple(jobs)
    reason: BackgroundJobBackpressureReason | None = None
    if (policy.idle_only or job.resource_profile.idle_only) and not idle_available:
        reason = BackgroundJobBackpressureReason.IDLE_ONLY_NOT_AVAILABLE
    elif _pending_count(materialized_jobs, job.kind) >= policy.max_pending_jobs:
        reason = BackgroundJobBackpressureReason.MAX_PENDING_JOBS
    elif _leased_counts(materialized_jobs, now)[job.kind] >= policy.concurrency_limit:
        reason = BackgroundJobBackpressureReason.KIND_CONCURRENCY_SATURATED
    elif _retryable_count(materialized_jobs, job.kind) >= policy.max_pending_jobs:
        reason = BackgroundJobBackpressureReason.RETRY_STORM_PREVENTION
    return reason


def _is_leaseable(job: BackgroundJobRecord, now: datetime) -> bool:
    lease_expired = job.status is BackgroundJobStatus.LEASED and (
        job.leased_until is not None and job.leased_until <= now
    )
    ready = job.status in _QUEUE_DEPTH_STATUSES
    return (ready or lease_expired) and job.not_before <= now


def _active_lease(job: BackgroundJobRecord, now: datetime) -> bool:
    return (
        job.status is BackgroundJobStatus.LEASED
        and job.leased_until is not None
        and job.leased_until > now
    )


def _leased_counts(
    jobs: Iterable[BackgroundJobRecord],
    now: datetime,
) -> Counter[BackgroundJobKind]:
    return Counter(job.kind for job in jobs if _active_lease(job, now))


def _pending_count(jobs: Iterable[BackgroundJobRecord], kind: BackgroundJobKind) -> int:
    return sum(1 for job in jobs if job.kind is kind and job.status is BackgroundJobStatus.PENDING)


def _retryable_count(jobs: Iterable[BackgroundJobRecord], kind: BackgroundJobKind) -> int:
    return sum(
        1 for job in jobs if job.kind is kind and job.status is BackgroundJobStatus.FAILED_RETRYABLE
    )


def _job_kinds(jobs: Iterable[BackgroundJobRecord]) -> set[BackgroundJobKind]:
    return {job.kind for job in jobs}


def _kind_sort_key(kind: BackgroundJobKind) -> str:
    return kind.value


def _metrics_from_jobs(
    jobs: Iterable[BackgroundJobRecord],
    now: datetime,
) -> BackgroundJobQueueMetrics:
    materialized_jobs = tuple(jobs)
    kinds = tuple(sorted(_job_kinds(materialized_jobs), key=_kind_sort_key))
    per_kind = tuple(_kind_metrics(kind, materialized_jobs, now) for kind in kinds)
    return BackgroundJobQueueMetrics(
        generated_at=now,
        queue_depth=sum(metrics.queue_depth for metrics in per_kind),
        leased=sum(metrics.leased for metrics in per_kind),
        succeeded=sum(metrics.succeeded for metrics in per_kind),
        failed_retryable=sum(metrics.failed_retryable for metrics in per_kind),
        failed_permanent=sum(metrics.failed_permanent for metrics in per_kind),
        cancelled=sum(metrics.cancelled for metrics in per_kind),
        oldest_pending_age_seconds=_oldest_pending_age_seconds(materialized_jobs, now),
        per_kind=per_kind,
    )


def _kind_metrics(
    kind: BackgroundJobKind,
    jobs: Iterable[BackgroundJobRecord],
    now: datetime,
) -> BackgroundJobKindMetrics:
    kind_jobs = tuple(job for job in jobs if job.kind is kind)
    return BackgroundJobKindMetrics(
        kind=kind,
        pending=_status_count(kind_jobs, BackgroundJobStatus.PENDING),
        leased=sum(1 for job in kind_jobs if _active_lease(job, now)),
        succeeded=_status_count(kind_jobs, BackgroundJobStatus.SUCCEEDED),
        failed_retryable=_status_count(kind_jobs, BackgroundJobStatus.FAILED_RETRYABLE),
        failed_permanent=_status_count(kind_jobs, BackgroundJobStatus.FAILED_PERMANENT),
        cancelled=_status_count(kind_jobs, BackgroundJobStatus.CANCELLED),
        oldest_pending_age_seconds=_oldest_pending_age_seconds(kind_jobs, now),
    )


def _status_count(jobs: Iterable[BackgroundJobRecord], status: BackgroundJobStatus) -> int:
    return sum(1 for job in jobs if job.status is status)


def _oldest_pending_age_seconds(
    jobs: Iterable[BackgroundJobRecord],
    now: datetime,
) -> float | None:
    created_values = tuple(
        job.created_at
        for job in jobs
        if job.status in _QUEUE_DEPTH_STATUSES and job.not_before <= now
    )
    if not created_values:
        return None
    return (now - min(created_values)).total_seconds()


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
        resource_profile=job.resource_profile,
        leased_until=update.leased_until,
        idempotency_key=job.idempotency_key,
        created_at=job.created_at,
        updated_at=update.updated_at,
        last_error=update.last_error,
        defer_reason=job.defer_reason,
    )
