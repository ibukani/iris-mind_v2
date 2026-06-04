"""メモリストレージアダプタ境界のポート。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.contracts.memory import MemoryQuery, MemoryRecord, MemorySearchResult


class MemoryStore(Protocol):
    """メモリストレージバックエンドのプロトコル。"""

    def search(self, query: MemoryQuery) -> Sequence[MemorySearchResult]:
        """クエリに一致するメモリレコードを検索する。"""
        ...

    def put(self, record: MemoryRecord) -> None:
        """メモリレコードを保存する。"""
