"""シンプルなインメモリ・テキスト合致MemoryStore実装。

埋め込み関数や永続化なしで完全な `MutableMemoryStore` 契約を満たす。
決定論的なテスト/ローカル配線用。
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, override

from iris.contracts.memory import MutableMemoryStore
from iris.adapters.memory.utils import matches_query, rank_text_matches

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.contracts.memory import (
        MemoryId,
        MemoryQuery,
        MemoryRecord,
        MemorySearchResult,
    )


class InMemoryMemoryStore(MutableMemoryStore):
    """永続化なしのテキスト合致インメモリMemoryStore。"""

    def __init__(self, records: Sequence[MemoryRecord] = ()) -> None:
        """オプションのシードレコードで初期化する。

        Args:
            records: ストアに投入する初期メモリレコード。
        """
        self._records: list[MemoryRecord] = []
        for record in records:
            self._upsert(record)

    def _upsert(self, record: MemoryRecord) -> None:
        for index, existing in enumerate(self._records):
            if existing.id == record.id:
                self._records[index] = record
                return
        self._records.append(record)

    @override
    def put(self, record: MemoryRecord) -> None:
        """メモリレコードを保存する。"""
        self._records.append(record)

    @override
    def get(self, memory_id: MemoryId) -> MemoryRecord | None:
        """指定 ID のレコードを返す。

        Returns:
            MemoryRecord | None: 一致するレコード。存在しない場合は None。
        """
        for record in self._records:
            if record.id == memory_id:
                return record
        return None

    @override
    def update(self, record: MemoryRecord) -> MemoryRecord:
        """既存レコードを upsert する。

        Returns:
            MemoryRecord: 永続化された正規化済みレコード。
        """
        self._upsert(record)
        return record

    @override
    def archive(self, memory_id: MemoryId, *, archived: bool = True) -> MemoryRecord | None:
        """指定 ID のアーカイブ状態を切り替える。

        Returns:
            MemoryRecord | None: 更新後レコード。存在しない ID の場合は None。
        """
        for index, existing in enumerate(self._records):
            if existing.id == memory_id:
                if existing.archived == archived:
                    return existing
                updated = dataclasses.replace(existing, archived=archived)
                self._records[index] = updated
                return updated
        return None

    @override
    def filter(self, query: MemoryQuery) -> Sequence[MemoryRecord]:
        """スコープ/種別/アーカイブ状態でフィルタしたレコードを返す。

        Returns:
            Sequence[MemoryRecord]: フィルタ条件に一致したレコードのシーケンス。
        """
        return tuple(record for record in self._records if matches_query(record, query))

    @override
    def search(self, query: MemoryQuery) -> Sequence[MemorySearchResult]:
        """トークン重複カウントによるテキスト合致検索。

        Returns:
            Sequence[MemorySearchResult]: スコア降順の検索結果。
        """
        return rank_text_matches(self.filter(query), query)
