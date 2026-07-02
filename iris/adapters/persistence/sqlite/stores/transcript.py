"""SQLite-backed transcript store。"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from iris.adapters.persistence.sqlite.database import SQLiteDatabase
from iris.adapters.persistence.sqlite.migrator import SQLiteSchemaMigrator
from iris.adapters.persistence.sqlite.serialization import (
    datetime_to_text,
    optional_datetime,
    optional_new_type,
    optional_text,
    required_datetime_to_text,
    text_to_datetime,
)
from iris.contracts.transcript import (
    TranscriptPruneResult,
    TranscriptQuery,
    TranscriptRecord,
    TranscriptRole,
    TranscriptSource,
    TranscriptSubjectKind,
)
from iris.core.ids import AccountId, ActorId, ObservationId, SessionId, SpaceId, TranscriptId

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path
    import sqlite3


class SQLiteTranscriptStore:
    """SQLite-backed confirmed conversation transcript store。"""

    def __init__(
        self,
        db_path: str | Path,
        *,
        ensure_schema: bool = True,
        migrator: SQLiteSchemaMigrator | None = None,
        max_records_per_key: int = 1000,
    ) -> None:
        """Migration 済み SQLite DB に接続する。"""
        if ensure_schema:
            (migrator or SQLiteSchemaMigrator()).ensure_current(db_path)
        self._db = SQLiteDatabase(db_path, synchronous="NORMAL")
        self._max_records_per_key = max_records_per_key

    def close(self) -> None:
        """永続 connection を閉じる。"""
        self._db.close()

    async def append(self, records: tuple[TranscriptRecord, ...]) -> None:
        """Transcript record を追記し、key 単位の上限を適用する。"""
        if not records:
            return
        await asyncio.to_thread(self._append_sync, records)

    async def query(self, query: TranscriptQuery) -> tuple[TranscriptRecord, ...]:
        """境界付き query で transcript record を取得する。

        Returns:
            時系列順の transcript record。
        """
        return await asyncio.to_thread(self._query_sync, query)

    async def prune_expired(self, now: datetime) -> TranscriptPruneResult:
        """保持期限を過ぎた transcript record を削除する。

        Returns:
            削除した record 件数。
        """
        return await asyncio.to_thread(self._prune_expired_sync, now)

    def _append_sync(self, records: tuple[TranscriptRecord, ...]) -> None:
        with self._db.transaction(immediate=True) as conn:
            for record in records:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO conversation_transcripts (
                        transcript_id, subject_kind, subject_id, space_id,
                        session_id, actor_id, account_id, observation_id, role,
                        source, content, occurred_at, recorded_at,
                        retention_until, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _record_to_row(record),
                )
                _prune_key_overflow(conn, record, self._max_records_per_key)

    def _query_sync(self, query: TranscriptQuery) -> tuple[TranscriptRecord, ...]:
        if query.limit <= 0:
            return ()
        params = _query_params(query)
        rows = self._db_query(params, query.limit)
        return tuple(_row_to_record(row) for row in rows)

    def _db_query(
        self,
        params: tuple[object, ...],
        limit: int,
    ) -> tuple[sqlite3.Row, ...]:
        with self._db.transaction() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM conversation_transcripts
                WHERE (? IS NULL OR subject_kind = ?)
                  AND (? IS NULL OR subject_id = ?)
                  AND (? IS NULL OR actor_id = ?)
                  AND (? IS NULL OR account_id = ?)
                  AND (? IS NULL OR space_id = ?)
                  AND (? IS NULL OR session_id = ?)
                ORDER BY occurred_at, transcript_id
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
        return tuple(rows)

    def _prune_expired_sync(self, now: datetime) -> TranscriptPruneResult:
        with self._db.transaction(immediate=True) as conn:
            cursor = conn.execute(
                """
                DELETE FROM conversation_transcripts
                WHERE retention_until IS NOT NULL AND retention_until <= ?
                """,
                (required_datetime_to_text(now),),
            )
            return TranscriptPruneResult(deleted_count=cursor.rowcount)


def _query_params(query: TranscriptQuery) -> tuple[object, ...]:
    return (
        _optional_query_text(query.subject_kind),
        _optional_query_text(query.subject_kind),
        _optional_query_text(query.subject_id),
        _optional_query_text(query.subject_id),
        _optional_query_text(query.actor_id),
        _optional_query_text(query.actor_id),
        _optional_query_text(query.account_id),
        _optional_query_text(query.account_id),
        _optional_query_text(query.space_id),
        _optional_query_text(query.space_id),
        _optional_query_text(query.session_id),
        _optional_query_text(query.session_id),
    )


def _optional_query_text(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _prune_key_overflow(
    conn: sqlite3.Connection,
    record: TranscriptRecord,
    max_records_per_key: int,
) -> None:
    if max_records_per_key <= 0:
        return
    conn.execute(
        """
        DELETE FROM conversation_transcripts
        WHERE transcript_id IN (
            SELECT transcript_id
            FROM conversation_transcripts
            WHERE subject_kind = ? AND subject_id = ? AND space_id IS ?
            ORDER BY occurred_at DESC, transcript_id DESC
            LIMIT -1 OFFSET ?
        )
        """,
        (
            str(record.subject_kind),
            record.subject_id,
            optional_text(record.space_id),
            max_records_per_key,
        ),
    )


def _record_to_row(record: TranscriptRecord) -> tuple[object, ...]:
    return (
        str(record.transcript_id),
        str(record.subject_kind),
        record.subject_id,
        optional_text(record.space_id),
        str(record.session_id),
        optional_text(record.actor_id),
        optional_text(record.account_id),
        optional_text(record.observation_id),
        str(record.role),
        str(record.source),
        record.content,
        required_datetime_to_text(record.occurred_at),
        required_datetime_to_text(record.recorded_at),
        datetime_to_text(record.retention_until),
        json.dumps(dict(record.metadata)),
    )


def _row_to_record(row: sqlite3.Row) -> TranscriptRecord:
    return TranscriptRecord(
        transcript_id=TranscriptId(str(row["transcript_id"])),
        subject_kind=TranscriptSubjectKind(str(row["subject_kind"])),
        subject_id=str(row["subject_id"]),
        role=TranscriptRole(str(row["role"])),
        source=TranscriptSource(str(row["source"])),
        content=str(row["content"]),
        occurred_at=text_to_datetime(str(row["occurred_at"])),
        recorded_at=text_to_datetime(str(row["recorded_at"])),
        session_id=SessionId(str(row["session_id"])),
        observation_id=optional_new_type(ObservationId, row["observation_id"]),
        actor_id=optional_new_type(ActorId, row["actor_id"]),
        account_id=optional_new_type(AccountId, row["account_id"]),
        space_id=optional_new_type(SpaceId, row["space_id"]),
        retention_until=optional_datetime(row["retention_until"]),
        metadata=json.loads(str(row["metadata_json"])),
    )
