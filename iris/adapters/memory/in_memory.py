"""シンプルなインメモリ・テキスト合致MemoryStore実装。

埋め込み関数や永続化なしで完全な `MutableMemoryStore` 契約を満たす。
決定論的なテスト/ローカル配線用。
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, override

from iris.adapters.memory.ports import MutableMemoryStore
from iris.contracts.memory import (
    MemoryId,
    MemoryQuery,
    MemoryRecord,
    MemorySearchResult,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


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
        results: list[MemoryRecord] = []
        for record in self._records:
            if query.actor_id is not None and record.actor_id != query.actor_id:
                continue
            if query.space_id is not None and record.space_id != query.space_id:
                continue
            if query.kind is not None and record.kind != query.kind:
                continue
            if not query.include_archived and record.archived:
                continue
            results.append(record)
        return tuple(results)

    @override
    def search(self, query: MemoryQuery) -> Sequence[MemorySearchResult]:
        """トークン重複カウントによるテキスト合致検索。

        Returns:
            Sequence[MemorySearchResult]: スコア降順の検索結果。
        """
        if query.limit <= 0:
            return ()

        eligible = self.filter(query)
        terms = tuple(term.casefold() for term in query.text.split() if term.strip())
        ranked: list[tuple[int, int, MemorySearchResult]] = []
        for index, record in enumerate(eligible):
            score = _score_record(record, terms)
            if score <= 0:
                continue
            ranked.append((score, index, MemorySearchResult(record=record, score=float(score))))

        ranked.sort(key=lambda item: (-item[0], item[1]))
        return tuple(result for _, _, result in ranked[: query.limit])


def _score_record(record: MemoryRecord, terms: tuple[str, ...]) -> int:
    if not terms:
        return 0
    text = record.text.casefold()
    return sum(1 for term in terms if term in text)
