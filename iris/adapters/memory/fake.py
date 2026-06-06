"""テスト用のフェイクインメモリMemoryStore。"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from iris.adapters.memory.in_memory import InMemoryMemoryStore

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.contracts.memory import MemoryQuery, MemoryRecord, MemorySearchResult


class FakeMemoryStore(InMemoryMemoryStore):
    """本番バックエンドなしでテストするためのインメモリMemoryStore。

    `InMemoryMemoryStore` の上に構築し、`fixed_results` モードで
    検索結果を完全に差し替える。
    """

    def __init__(
        self,
        records: Sequence[MemoryRecord] = (),
        *,
        fixed_results: Sequence[MemorySearchResult] | None = None,
    ) -> None:
        """オプションのシードレコードまたは固定検索結果で初期化する。

        Args:
            records: Initial memory records to populate the store.
            fixed_results: When set, search always returns a subset of these results.
        """
        super().__init__(records=records)
        self._fixed_results = tuple(fixed_results) if fixed_results is not None else None

    @override
    def search(self, query: MemoryQuery) -> Sequence[MemorySearchResult]:
        """テキスト用語マッチングでメモリレコードを検索する。

        `fixed_results` が設定されている場合はクエリを無視してそれを返す。

        Returns:
            Sequence[MemorySearchResult]: 検索条件に一致するメモリレコードのシーケンス。
        """
        if self._fixed_results is not None:
            return self._fixed_results[: query.limit]
        return super().search(query)
