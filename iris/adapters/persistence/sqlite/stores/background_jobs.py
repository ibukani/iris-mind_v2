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
    BackgroundJobStatus,
    DeferredLearningJobPayload,
    MemoryBackgroundJobPayload,
    RuntimeLearningCandidateJobPayload,
)
from iris.runtime.learning.queue import (
    BackgroundJobQueueError,
    JobUpdate,
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
            新規または同じ idempotency key の既存ジョブ。
        """
        return await asyncio.to_thread(self._enqueue_sync, job)

    async def lease_due(
        self,
        now: datetime,
        max_items: int,
        lease_seconds: float,
    ) -> tuple[BackgroundJobRecord, ...]:
        """期限到来済みジョブを lease する。

        Returns:
            Lease したジョブ。
        """
        return await asyncio.to_thread(self._lease_due_sync, now, max_items, lease_seconds)

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
            conn.execute(
                """
                INSERT INTO background_jobs (
                    job_id, kind, payload_type, payload_json, status, attempts,
                    max_attempts, not_before, leased_until, idempotency_key,
                    created_at, updated_at, last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _record_to_row(job),
            )
            return job

    def _lease_due_sync(
        self,
        now: datetime,
        max_items: int,
        lease_seconds: float,
    ) -> tuple[BackgroundJobRecord, ...]:
        if max_items <= 0:
            return ()
        leased_until = now + timedelta(seconds=lease_seconds)
        with self._db.transaction(immediate=True) as conn:
            records = _select_due(conn, now, max_items)
            return tuple(_lease_record(conn, record, now, leased_until) for record in records)

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


def _select_due(
    conn: sqlite3.Connection,
    now: datetime,
    max_items: int,
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
            max_items,
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
        SET status = ?, attempts = ?, not_before = ?, leased_until = ?,
            updated_at = ?, last_error = ?
        WHERE job_id = ?
        """,
        (
            record.status.value,
            record.attempts,
            required_datetime_to_text(record.not_before),
            datetime_to_text(record.leased_until),
            required_datetime_to_text(record.updated_at),
            record.last_error,
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
        datetime_to_text(record.leased_until),
        record.idempotency_key,
        required_datetime_to_text(record.created_at),
        required_datetime_to_text(record.updated_at),
        record.last_error,
    )


def _row_to_record(row: sqlite3.Row) -> BackgroundJobRecord:
    return BackgroundJobRecord(
        job_id=BackgroundJobId(row["job_id"]),
        kind=BackgroundJobKind(row["kind"]),
        payload=_payload_from_json(_PayloadType(row["payload_type"]), row["payload_json"]),
        status=BackgroundJobStatus(row["status"]),
        attempts=int(row["attempts"]),
        max_attempts=int(row["max_attempts"]),
        not_before=text_to_datetime(row["not_before"]),
        leased_until=optional_datetime(row["leased_until"]),
        idempotency_key=row["idempotency_key"],
        created_at=text_to_datetime(row["created_at"]),
        updated_at=text_to_datetime(row["updated_at"]),
        last_error=row["last_error"],
    )


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
