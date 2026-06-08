"""ハイブリッドメモリ検索を認知サイクル配線に統合するテスト。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.adapters.memory.sqlite import SQLiteMemoryStore
from iris.adapters.memory.vector_index import InMemoryVectorMemoryIndex
from iris.cognitive.memory.hybrid import HybridMemoryRetriever
from iris.cognitive.memory.retrieval import MemoryRetrievalStep
from iris.cognitive.memory.write import MemoryWriteStep
from iris.contracts.memory import MemoryId, MemoryQuery, MemoryRecord, MemorySearchResult
from iris.runtime.wiring.cognitive import (
    wire_affect_memory_aware_text_response_cognitive_cycle,
    wire_policy_affect_memory_aware_text_response_cognitive_cycle,
)
from iris.runtime.wiring.memory import (
    SQLiteFTS5MemoryRetriever,
    wire_sqlite_hybrid_memory_retriever,
)
from tests.helpers.private_access import get_private_attr

if TYPE_CHECKING:
    from pathlib import Path


def embed_text(text: str) -> tuple[float, float]:
    """Tea / coffee キーワードに基づく 2 次元埋め込み。

    Returns:
        tuple[float, float]: 埋め込みベクトル。
    """
    return (
        1.0 if "tea" in text.casefold() else 0.0,
        1.0 if "coffee" in text.casefold() else 0.0,
    )


class _FakeRetriever:
    """テスト用の固定結果レトリーバー。"""

    def __init__(self, results: tuple[MemorySearchResult, ...]) -> None:
        self._results = results

    def search(self, query: MemoryQuery) -> tuple[MemorySearchResult, ...]:
        """検索を実行する。

        Returns:
            tuple[MemorySearchResult, ...]: 検索結果。
        """
        _ = query
        return self._results


def test_wire_affect_cycle_uses_memory_retriever_over_store() -> None:
    """memory_retriever 指定時に memory_store より優先される。"""
    store = InMemoryMemoryStore()
    store.put(MemoryRecord(id=MemoryId("m1"), text="stored"))
    fake = _FakeRetriever(
        (MemorySearchResult(record=MemoryRecord(id=MemoryId("m2"), text="retrieved"), score=1.0),)
    )

    cycle = wire_affect_memory_aware_text_response_cognitive_cycle(
        memory_store=store,
        memory_retriever=fake,
    )

    steps = get_private_attr(cycle, "_steps")
    retrieval_steps = [s for s in steps if isinstance(s, MemoryRetrievalStep)]
    assert len(retrieval_steps) == 1
    assert get_private_attr(retrieval_steps[0], "_retriever") is fake


def test_wire_policy_cycle_passes_vector_index_to_write_step() -> None:
    """vector_index 指定時に MemoryWriteStep に渡される。"""
    store = InMemoryMemoryStore()
    vector_index = InMemoryVectorMemoryIndex(embed_text)

    cycle = wire_policy_affect_memory_aware_text_response_cognitive_cycle(
        memory_store=store,
        vector_index=vector_index,
    )

    steps = get_private_attr(cycle, "_steps")
    write_steps = [s for s in steps if isinstance(s, MemoryWriteStep)]
    assert len(write_steps) == 1
    assert get_private_attr(write_steps[0], "_vector_index") is vector_index


def test_sqlite_fts5_memory_retriever_delegates_to_store(tmp_path: Path) -> None:
    """SQLiteFTS5MemoryRetriever が store.search_fts5 に委譲する。"""
    store = SQLiteMemoryStore(tmp_path / "fts.db")
    store.put(MemoryRecord(id=MemoryId("m1"), text="green tea"))

    retriever = SQLiteFTS5MemoryRetriever(store)
    results = retriever.search(MemoryQuery(text="tea", limit=5))

    assert len(results) >= 1
    assert any(str(r.record.id) == "m1" for r in results)


def test_wire_sqlite_hybrid_returns_tuple(tmp_path: Path) -> None:
    """wire_sqlite_hybrid_memory_retriever がタプルを返す。

    HybridMemoryRetriever と VectorMemoryIndex の両方を返すことを確認する。
    """
    store = SQLiteMemoryStore(tmp_path / "hybrid.db")

    hybrid, vector_index = wire_sqlite_hybrid_memory_retriever(
        store=store,
        embed_text=embed_text,
    )

    assert isinstance(hybrid, HybridMemoryRetriever)
    assert isinstance(vector_index, InMemoryVectorMemoryIndex)
