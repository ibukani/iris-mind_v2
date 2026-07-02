"""Transcript test helpers。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from iris.contracts.transcript import (
    TranscriptPruneResult,
    TranscriptQuery,
    TranscriptRecord,
    TranscriptRole,
    TranscriptSource,
    TranscriptSubjectKind,
)
from iris.core.ids import SessionId, TranscriptId


def make_transcript_record(transcript_id: str, content: str) -> TranscriptRecord:
    """テスト用 transcript record を作成する。

    Returns:
        境界テストで使う TranscriptRecord。
    """
    now = datetime(2026, 7, 1, tzinfo=UTC)
    return TranscriptRecord(
        transcript_id=TranscriptId(transcript_id),
        subject_kind=TranscriptSubjectKind.SESSION,
        subject_id="session-1",
        role=TranscriptRole.USER,
        source=TranscriptSource.INLINE_RESPONSE,
        content=content,
        occurred_at=now,
        recorded_at=now,
        session_id=SessionId("session-1"),
    )


class InMemoryTranscriptStore:
    """テスト用の境界付き transcript store。"""

    def __init__(self) -> None:
        """空の store を作成する。"""
        self._records: tuple[TranscriptRecord, ...] = ()
        self._lock = asyncio.Lock()

    async def append(self, records: tuple[TranscriptRecord, ...]) -> None:
        """Record を追記する。"""
        async with self._lock:
            self._records += records

    async def query(self, query: TranscriptQuery) -> tuple[TranscriptRecord, ...]:
        """Query 条件に一致する record を返す。

        Returns:
            条件に一致した record。
        """
        async with self._lock:
            records = tuple(record for record in self._records if _matches(record, query))
            return records[: query.limit]

    async def prune_expired(self, now: datetime) -> TranscriptPruneResult:
        """期限切れ record を削除する。

        Returns:
            削除件数。
        """
        async with self._lock:
            kept = tuple(
                record
                for record in self._records
                if record.retention_until is None or record.retention_until > now
            )
            deleted = len(self._records) - len(kept)
            self._records = kept
            return TranscriptPruneResult(deleted_count=deleted)


def _matches(record: TranscriptRecord, query: TranscriptQuery) -> bool:
    return all(
        (
            query.subject_kind is None or record.subject_kind is query.subject_kind,
            query.subject_id is None or record.subject_id == query.subject_id,
            query.actor_id is None or record.actor_id == query.actor_id,
            query.account_id is None or record.account_id == query.account_id,
            query.space_id is None or record.space_id == query.space_id,
            query.session_id is None or record.session_id == query.session_id,
        )
    )
