"""Transcript persistence store ports and process-local null implementation。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from iris.contracts.transcript import TranscriptPruneResult

if TYPE_CHECKING:
    from datetime import datetime

    from iris.contracts.transcript import TranscriptQuery, TranscriptRecord


class TranscriptStore(Protocol):
    """確定済み transcript record の永続化境界。"""

    async def append(self, records: tuple[TranscriptRecord, ...]) -> None:
        """Transcript record を追記する。"""
        ...

    async def query(self, query: TranscriptQuery) -> tuple[TranscriptRecord, ...]:
        """境界付き query で transcript record を取得する。"""
        ...

    async def prune_expired(self, now: datetime) -> TranscriptPruneResult:
        """保持期限を過ぎた transcript record を削除する。"""
        ...


class NullTranscriptStore:
    """Transcript persistence を無効化する no-op store。"""

    def __init__(self) -> None:
        """No-op store を初期化する。"""
        self._ignored_record_count = 0

    async def append(self, records: tuple[TranscriptRecord, ...]) -> None:
        """Record を保存せずに破棄する。"""
        self._ignored_record_count += len(records)

    async def query(self, query: TranscriptQuery) -> tuple[TranscriptRecord, ...]:
        """保存無効時は常に空集合を返す。

        Returns:
            空の transcript record 集合。
        """
        if query.limit <= 0 and self._ignored_record_count == 0:
            return ()
        return ()

    async def prune_expired(self, now: datetime) -> TranscriptPruneResult:
        """保存無効時は削除対象なしを返す。

        Returns:
            削除件数 0。
        """
        if now.tzinfo is None and self._ignored_record_count == 0:
            return TranscriptPruneResult(deleted_count=0)
        return TranscriptPruneResult(deleted_count=0)
