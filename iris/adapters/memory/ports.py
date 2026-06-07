"""メモリストレージアダプタ境界のポート。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.contracts.memory import MemoryId, MemoryQuery, MemoryRecord, MemorySearchResult


class MemoryStore(Protocol):
    """メモリストレージバックエンドのプロトコル。

    検索/取得専用の最小契約。LangChain/ベクター型など書き込み API
    を持たない外部バックエンドの互換性のために維持される。
    """

    def search(self, query: MemoryQuery) -> Sequence[MemorySearchResult]:
        """クエリに一致するメモリレコードを検索する。"""
        ...

    def put(self, record: MemoryRecord) -> None:
        """メモリレコードを保存する。"""
        ...


class MutableMemoryStore(MemoryStore, Protocol):
    """可変なメモリストレージバックエンドのプロトコル。

    永続化や更新が必要なバックエンドの完全な CRUD 契約。
    """

    def get(self, memory_id: MemoryId) -> MemoryRecord | None:
        """指定 ID のメモリレコードを返す。存在しない場合は None。"""
        ...

    def update(self, record: MemoryRecord) -> MemoryRecord:
        """既存レコードを upsert して正規化された状態を返す。"""
        ...

    def archive(self, memory_id: MemoryId, *, archived: bool = True) -> MemoryRecord | None:
        """指定 ID のアーカイブ状態を切り替えて、対象レコードを返す。"""
        ...

    def filter(self, query: MemoryQuery) -> Sequence[MemoryRecord]:
        """スコープ/種別/アーカイブ状態などでフィルタしたレコードを返す。"""
        ...
