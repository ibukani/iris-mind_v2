"""SQLite-backed durable BackgroundJobQueue implementation。"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

from iris.adapters.persistence.sqlite.database import SQLiteDatabase
from iris.adapters.persistence.sqlite.migrator import SQLiteSchemaMigrator
from iris.adapters.persistence.sqlite.serialization import (
    datetime_to_text,
    optional_datetime,
    required_datetime_to_text,
    text_to_datetime,
)
from iris.runtime.learning.jobs import (
    BackgroundJobId,
    BackgroundJobKind,
    BackgroundJobRecord,
    BackgroundJobResourceProfile,
    BackgroundJobStatus,
    DeferredLearningJobPayload,
    MemoryBackgroundJobPayload,
    RuntimeLearningCandidateJobPayload,
)
from iris.runtime.learning.queue import (
    BackgroundJobBackpressureMode,
    BackgroundJobEnqueueDecision,
    BackgroundJobEnqueueResult,
    BackgroundJobKindMetrics,
    BackgroundJobKindPolicy,
    BackgroundJobQueueError,
    BackgroundJobQueueMetrics,
    BackgroundJobQueuePolicy,
    JobUpdate,
    defer_job_record,
    evaluate_enqueue_backpressure,
    replace_job,
    retry_failure_status,
)

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path
    import sqlite3


type _PayloadModel = (
    MemoryBackgroundJobPayload | RuntimeLearningCandidateJobPayload | DeferredLearningJobPayload
)


class _PayloadType(StrEnum):
    """SQLite payload_type に保存する tagged payload 種別。"""

    MEMORY_BACKGROUND = "memory_background"
    RUNTIME_LEARNING_CANDIDATE = "runtime_learning_candidate"
    DEFERRED_LEARNING = "deferred_learning"


class SQLiteBackgroundJobQueue:
    """SQLite-backed durable background job queue。

    通常の async 呼び出しでは同期 sqlite3 I/O を ``asyncio.to_thread`` へ逃がす。
    Lease 取得は ``BEGIN IMMEDIATE`` で read-modify-write を保護する。
    """

    def __init__(
        self,
        db_path: str | Path,
        *,
        ensure_schema: bool = True,
        migrator: SQLiteSchemaMigrator | None = None,
    ) -> None:
        """Migration 済み SQLite DB に接続する。"""
        if ensure_schema:
            (migrator or SQLiteSchemaMigrator()).ensure_current(db_path)
        self._db = SQLiteDatabase(db_path, synchronous="NORMAL")

    def close(self) -> None:
        """永続 connection を閉じる。"""
        self._db.close()

    async def enqueue(self, job: BackgroundJobRecord) -> BackgroundJobRecord:
        """ジョブを冪等に登録する。

        Returns:
            新規または同じ idempotency key / job_id の既存ジョブ。
        """
        return await asyncio.to_thread(self._enqueue_sync, job)

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
        return await asyncio.to_thread(
            self._enqueue_with_policy_sync,
            job,
            now,
            policy,
            idle_available=idle_available,
        )

    async def lease_due(
        self,
        now: datetime,
        max_items: int,
        lease_seconds: float,
        *,
        policy: BackgroundJobQueuePolicy | None = None,
        idle_available: bool = False,
    ) -> tuple[BackgroundJobRecord, ...]:
        """期限到来済みジョブを lease する。

        Returns:
            Lease したジョブ。
        """
        return await asyncio.to_thread(
            self._lease_due_sync,
            now,
            max_items,
            lease_seconds,
            policy,
            idle_available=idle_available,
        )

    async def collect_metrics(self, now: datetime) -> BackgroundJobQueueMetrics:
        """現在の queue metrics snapshot を返す。

        Returns:
            queue metrics snapshot。
        """
        return await asyncio.to_thread(self._collect_metrics_sync, now)

    async def mark_succeeded(self, job_id: BackgroundJobId, finished_at: datetime) -> None:
        """Lease 中ジョブを成功完了にする。"""
        await asyncio.to_thread(
            self._update_terminal_sync,
            job_id,
            BackgroundJobStatus.SUCCEEDED,
            finished_at,
            None,
        )

    async def mark_retryable_failure(
        self,
        job_id: BackgroundJobId,
        failed_at: datetime,
        reason: str,
        retry_after: datetime,
    ) -> None:
        """試行回数を増やし、再試行または恒久失敗へ遷移する。"""
        await asyncio.to_thread(
            self._mark_retryable_failure_sync,
            job_id,
            failed_at,
            reason,
            retry_after,
        )

    async def mark_permanent_failure(
        self, job_id: BackgroundJobId, failed_at: datetime, reason: str
    ) -> None:
        """ジョブを恒久失敗にする。"""
        await asyncio.to_thread(
            self._update_terminal_sync,
            job_id,
            BackgroundJobStatus.FAILED_PERMANENT,
            failed_at,
            reason,
        )

    async def get(self, job_id: BackgroundJobId) -> BackgroundJobRecord:
        """ジョブを取得する。

        Returns:
            指定 ID のジョブ。
        """
        return await asyncio.to_thread(self._get_required_sync, job_id)

    def _enqueue_sync(self, job: BackgroundJobRecord) -> BackgroundJobRecord:
        with self._db.transaction(immediate=True) as conn:
            existing = _find_existing(conn, job)
            if existing is not None:
                return existing
            _insert(conn, job)
            return job

    def _enqueue_with_policy_sync(
        self,
        job: BackgroundJobRecord,
        now: datetime,
        policy: BackgroundJobQueuePolicy,
        *,
        idle_available: bool,
    ) -> BackgroundJobEnqueueResult:
        with self._db.transaction(immediate=True) as conn:
            existing = _find_existing(conn, job)
            if existing is not None:
                return BackgroundJobEnqueueResult(
                    decision=BackgroundJobEnqueueDecision.EXISTING,
                    record=existing,
                )
            jobs = _select_all(conn)
            reason = evaluate_enqueue_backpressure(
                job,
                jobs=jobs,
                now=now,
                policy=policy.for_kind(job.kind),
                idle_available=idle_available,
            )
            kind_policy = policy.for_kind(job.kind)
            if (
                reason is None
                or kind_policy.backpressure_mode is BackgroundJobBackpressureMode.ACCEPT
            ):
                _insert(conn, job)
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
            _insert(conn, deferred)
            return BackgroundJobEnqueueResult(
                decision=BackgroundJobEnqueueDecision.DEFERRED,
                record=deferred,
                reason=reason,
                deferred_until=deferred_until,
            )

    def _lease_due_sync(
        self,
        now: datetime,
        max_items: int,
        lease_seconds: float,
        policy: BackgroundJobQueuePolicy | None,
        *,
        idle_available: bool,
    ) -> tuple[BackgroundJobRecord, ...]:
        if max_items <= 0:
            return ()
        leased_until = now + timedelta(seconds=lease_seconds)
        with self._db.transaction(immediate=True) as conn:
            records = _select_due(conn, now, max_items=None if policy is not None else max_items)
            leased_counts = _leased_counts(conn, now)
            leased: list[BackgroundJobRecord] = []
            for record in records:
                kind_policy = policy.for_kind(record.kind) if policy is not None else None
                if _requires_idle(record, kind_policy) and not idle_available:
                    continue
                if (
                    kind_policy is not None
                    and leased_counts.get(record.kind, 0) >= kind_policy.concurrency_limit
                ):
                    continue
                leased_record = _lease_record(conn, record, now, leased_until)
                leased_counts[record.kind] = leased_counts.get(record.kind, 0) + 1
                leased.append(leased_record)
                if len(leased) >= max_items:
                    break
            return tuple(leased)

    def _collect_metrics_sync(self, now: datetime) -> BackgroundJobQueueMetrics:
        with self._db.transaction() as conn:
            records = _select_all(conn)
        per_kind = tuple(_kind_metrics(kind, records, now) for kind in _sorted_kinds(records))
        return BackgroundJobQueueMetrics(
            generated_at=now,
            queue_depth=sum(metrics.queue_depth for metrics in per_kind),
            leased=sum(metrics.leased for metrics in per_kind),
            succeeded=sum(metrics.succeeded for metrics in per_kind),
            failed_retryable=sum(metrics.failed_retryable for metrics in per_kind),
            failed_permanent=sum(metrics.failed_permanent for metrics in per_kind),
            cancelled=sum(metrics.cancelled for metrics in per_kind),
            oldest_pending_age_seconds=_oldest_pending_age_seconds(records, now),
            per_kind=per_kind,
        )

    def _mark_retryable_failure_sync(
        self,
        job_id: BackgroundJobId,
        failed_at: datetime,
        reason: str,
        retry_after: datetime,
    ) -> None:
        with self._db.transaction(immediate=True) as conn:
            job = _require(conn, job_id)
            attempts = job.attempts + 1
            status = retry_failure_status(attempts=attempts, max_attempts=job.max_attempts)
            _update(
                conn,
                replace_job(
                    job,
                    JobUpdate(
                        status=status,
                        attempts=attempts,
                        not_before=retry_after,
                        leased_until=None,
                        updated_at=failed_at,
                        last_error=reason,
                    ),
                ),
            )

    def _update_terminal_sync(
        self,
        job_id: BackgroundJobId,
        status: BackgroundJobStatus,
        updated_at: datetime,
        error: str | None,
    ) -> None:
        with self._db.transaction(immediate=True) as conn:
            job = _require(conn, job_id)
            _update(
                conn,
                replace_job(
                    job,
                    JobUpdate(
                        status=status,
                        leased_until=None,
                        updated_at=updated_at,
                        last_error=error,
                    ),
                ),
            )

    def _get_required_sync(self, job_id: BackgroundJobId) -> BackgroundJobRecord:
        with self._db.transaction() as conn:
            return _require(conn, job_id)


def _insert(conn: sqlite3.Connection, job: BackgroundJobRecord) -> None:
    conn.execute(
        """
        INSERT INTO background_jobs (
            job_id, kind, payload_type, payload_json, status, attempts,
            max_attempts, not_before, resource_profile_json, leased_until,
            idempotency_key, created_at, updated_at, last_error, defer_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        _record_to_row(job),
    )


def _find_existing(
    conn: sqlite3.Connection,
    job: BackgroundJobRecord,
) -> BackgroundJobRecord | None:
    row = conn.execute(
        """
        SELECT *
        FROM background_jobs
        WHERE job_id = ? OR idempotency_key = ?
        ORDER BY CASE WHEN job_id = ? THEN 0 ELSE 1 END
        LIMIT 1
        """,
        (str(job.job_id), job.idempotency_key, str(job.job_id)),
    ).fetchone()
    if row is None:
        return None
    return _row_to_record(row)


def _select_all(conn: sqlite3.Connection) -> tuple[BackgroundJobRecord, ...]:
    rows = conn.execute(
        """
        SELECT *
        FROM background_jobs
        ORDER BY not_before, created_at, job_id
        """
    ).fetchall()
    return tuple(_row_to_record(row) for row in rows)


def _select_due(
    conn: sqlite3.Connection,
    now: datetime,
    max_items: int | None,
) -> tuple[BackgroundJobRecord, ...]:
    now_text = required_datetime_to_text(now)
    rows = conn.execute(
        """
        SELECT *
        FROM background_jobs
        WHERE (
            status IN (?, ?)
            OR (status = ? AND leased_until IS NOT NULL AND leased_until <= ?)
        )
        AND not_before <= ?
        ORDER BY not_before, created_at, job_id
        LIMIT ?
        """,
        (
            BackgroundJobStatus.PENDING.value,
            BackgroundJobStatus.FAILED_RETRYABLE.value,
            BackgroundJobStatus.LEASED.value,
            now_text,
            now_text,
            -1 if max_items is None else max_items,
        ),
    ).fetchall()
    return tuple(_row_to_record(row) for row in rows)


def _lease_record(
    conn: sqlite3.Connection,
    record: BackgroundJobRecord,
    now: datetime,
    leased_until: datetime,
) -> BackgroundJobRecord:
    updated = replace_job(
        record,
        JobUpdate(
            status=BackgroundJobStatus.LEASED,
            leased_until=leased_until,
            updated_at=now,
        ),
    )
    _update(conn, updated)
    return updated


def _leased_counts(
    conn: sqlite3.Connection,
    now: datetime,
) -> dict[BackgroundJobKind, int]:
    now_text = required_datetime_to_text(now)
    rows = conn.execute(
        """
        SELECT kind, COUNT(*) AS count
        FROM background_jobs
        WHERE status = ?
          AND leased_until IS NOT NULL
          AND leased_until > ?
        GROUP BY kind
        """,
        (BackgroundJobStatus.LEASED.value, now_text),
    ).fetchall()
    return {BackgroundJobKind(row["kind"]): int(row["count"]) for row in rows}


def _require(conn: sqlite3.Connection, job_id: BackgroundJobId) -> BackgroundJobRecord:
    row = conn.execute(
        "SELECT * FROM background_jobs WHERE job_id = ?",
        (str(job_id),),
    ).fetchone()
    if row is None:
        message = f"unknown background job: {job_id}"
        raise BackgroundJobQueueError(message)
    return _row_to_record(row)


def _update(conn: sqlite3.Connection, record: BackgroundJobRecord) -> None:
    conn.execute(
        """
        UPDATE background_jobs
        SET status = ?, attempts = ?, not_before = ?, resource_profile_json = ?,
            leased_until = ?, updated_at = ?, last_error = ?, defer_reason = ?
        WHERE job_id = ?
        """,
        (
            record.status.value,
            record.attempts,
            required_datetime_to_text(record.not_before),
            record.resource_profile.model_dump_json(),
            datetime_to_text(record.leased_until),
            required_datetime_to_text(record.updated_at),
            record.last_error,
            record.defer_reason,
            str(record.job_id),
        ),
    )


def _record_to_row(record: BackgroundJobRecord) -> tuple[object, ...]:
    payload_type = _payload_type(record.payload)
    return (
        str(record.job_id),
        record.kind.value,
        payload_type.value,
        _payload_to_json(record.payload),
        record.status.value,
        record.attempts,
        record.max_attempts,
        required_datetime_to_text(record.not_before),
        record.resource_profile.model_dump_json(),
        datetime_to_text(record.leased_until),
        record.idempotency_key,
        required_datetime_to_text(record.created_at),
        required_datetime_to_text(record.updated_at),
        record.last_error,
        record.defer_reason,
    )


def _row_to_record(row: sqlite3.Row) -> BackgroundJobRecord:
    resource_profile_json = row["resource_profile_json"]
    return BackgroundJobRecord(
        job_id=BackgroundJobId(row["job_id"]),
        kind=BackgroundJobKind(row["kind"]),
        payload=_payload_from_json(_PayloadType(row["payload_type"]), row["payload_json"]),
        status=BackgroundJobStatus(row["status"]),
        attempts=int(row["attempts"]),
        max_attempts=int(row["max_attempts"]),
        not_before=text_to_datetime(row["not_before"]),
        resource_profile=BackgroundJobResourceProfile.model_validate_json(resource_profile_json),
        leased_until=optional_datetime(row["leased_until"]),
        idempotency_key=row["idempotency_key"],
        created_at=text_to_datetime(row["created_at"]),
        updated_at=text_to_datetime(row["updated_at"]),
        last_error=row["last_error"],
        defer_reason=row["defer_reason"],
    )


def _kind_metrics(
    kind: BackgroundJobKind,
    jobs: tuple[BackgroundJobRecord, ...],
    now: datetime,
) -> BackgroundJobKindMetrics:
    kind_jobs = tuple(job for job in jobs if job.kind is kind)
    return BackgroundJobKindMetrics(
        kind=kind,
        pending=sum(1 for job in kind_jobs if _is_backlog_pending(job, now)),
        leased=sum(1 for job in kind_jobs if _active_lease(job, now)),
        succeeded=_status_count(kind_jobs, BackgroundJobStatus.SUCCEEDED),
        failed_retryable=_status_count(kind_jobs, BackgroundJobStatus.FAILED_RETRYABLE),
        failed_permanent=_status_count(kind_jobs, BackgroundJobStatus.FAILED_PERMANENT),
        cancelled=_status_count(kind_jobs, BackgroundJobStatus.CANCELLED),
        oldest_pending_age_seconds=_oldest_pending_age_seconds(kind_jobs, now),
    )


def _sorted_kinds(jobs: tuple[BackgroundJobRecord, ...]) -> tuple[BackgroundJobKind, ...]:
    return tuple(sorted({job.kind for job in jobs}, key=lambda kind: kind.value))


def _active_lease(job: BackgroundJobRecord, now: datetime) -> bool:
    return (
        job.status is BackgroundJobStatus.LEASED
        and job.leased_until is not None
        and job.leased_until > now
    )


def _status_count(jobs: tuple[BackgroundJobRecord, ...], status: BackgroundJobStatus) -> int:
    return sum(1 for job in jobs if job.status is status)


def _is_expired_lease(job: BackgroundJobRecord, now: datetime) -> bool:
    return (
        job.status is BackgroundJobStatus.LEASED
        and job.leased_until is not None
        and job.leased_until <= now
    )


def _is_backlog_pending(job: BackgroundJobRecord, now: datetime) -> bool:
    return (job.status is BackgroundJobStatus.PENDING or _is_expired_lease(job, now)) and (
        job.not_before <= now
    )


def _requires_idle(
    job: BackgroundJobRecord,
    kind_policy: BackgroundJobKindPolicy | None,
) -> bool:
    return job.resource_profile.idle_only or (kind_policy is not None and kind_policy.idle_only)


def _oldest_pending_age_seconds(
    jobs: tuple[BackgroundJobRecord, ...],
    now: datetime,
) -> float | None:
    created_values = tuple(
        job.created_at
        for job in jobs
        if (job.status is BackgroundJobStatus.FAILED_RETRYABLE or _is_backlog_pending(job, now))
        and job.not_before <= now
    )
    if not created_values:
        return None
    return (now - min(created_values)).total_seconds()


def _payload_type(payload: _PayloadModel) -> _PayloadType:
    if isinstance(payload, MemoryBackgroundJobPayload):
        return _PayloadType.MEMORY_BACKGROUND
    if isinstance(payload, RuntimeLearningCandidateJobPayload):
        return _PayloadType.RUNTIME_LEARNING_CANDIDATE
    return _PayloadType.DEFERRED_LEARNING


def _payload_to_json(payload: _PayloadModel) -> str:
    return payload.model_dump_json()


def _payload_from_json(payload_type: _PayloadType, payload_json: str) -> _PayloadModel:
    if payload_type is _PayloadType.MEMORY_BACKGROUND:
        return MemoryBackgroundJobPayload.model_validate_json(payload_json)
    if payload_type is _PayloadType.RUNTIME_LEARNING_CANDIDATE:
        return RuntimeLearningCandidateJobPayload.model_validate_json(payload_json)
    return DeferredLearningJobPayload.model_validate_json(payload_json)
