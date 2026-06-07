"""ハイブリッドメモリ検索配線のテスト。"""

from __future__ import annotations

from typing import override

from iris.adapters.memory.fake import FakeMemoryStore
from iris.adapters.memory.vector_index import InMemoryVectorMemoryIndex
from iris.cognitive.memory.hybrid import HybridMemoryRetriever
from iris.cognitive.memory.retrieval import MemoryRetriever
from iris.contracts.memory import MemoryId, MemoryQuery, MemoryRecord, MemorySearchResult
from iris.runtime.wiring.memory import wire_hybrid_memory_retriever


def embed_text(text: str) -> tuple[float, float]:
    """Tea / coffee キーワードに基づく 2 次元埋め込み。

    Args:
        text: 入力テキスト。

    Returns:
        tuple[float, float]: 埋め込みベクトル。
    """
    return (
        1.0 if "tea" in text.casefold() else 0.0,
        1.0 if "coffee" in text.casefold() else 0.0,
    )


class _SimpleFtsRetriever(MemoryRetriever):
    """テスト用の簡易 FTS5 retriever。"""

    def __init__(self, store: FakeMemoryStore) -> None:
        self._store = store

    @override
    def search(self, query: MemoryQuery) -> tuple[MemorySearchResult, ...]:
        """FTS5 検索を実行する。

        Returns:
            tuple[MemorySearchResult, ...]: 検索結果。
        """
        return tuple(self._store.search(query))


def test_wire_hybrid_memory_retriever_returns_hybrid() -> None:
    """wire_hybrid_memory_retriever が HybridMemoryRetriever を返す。"""
    store = FakeMemoryStore(
        records=(
            MemoryRecord(id=MemoryId("m1"), text="User likes green tea."),
            MemoryRecord(id=MemoryId("m2"), text="User prefers coffee."),
        )
    )
    fts = _SimpleFtsRetriever(store)
    vector = InMemoryVectorMemoryIndex(embed_text)
    vector.upsert(MemoryId("m1"), "User likes green tea.", {})
    vector.upsert(MemoryId("m2"), "User prefers coffee.", {})

    hybrid = wire_hybrid_memory_retriever(
        fts_retriever=fts,
        vector_index=vector,
        store=store,
    )

    assert isinstance(hybrid, HybridMemoryRetriever)
    results = hybrid.search(MemoryQuery(text="tea", limit=5))
    ids = [str(r.record.id) for r in results]
    assert "m1" in ids
