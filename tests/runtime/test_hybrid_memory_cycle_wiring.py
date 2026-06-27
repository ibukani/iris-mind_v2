"""ハイブリッドメモリ検索を認知サイクル配線に統合するテスト。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.adapters.memory.vector_index import InMemoryVectorMemoryIndex
from iris.adapters.sqlite.memory_store import SQLiteMemoryStore
from iris.cognitive.memory.retrieval import MemoryRetrievalStep
from iris.cognitive.memory.write import MemoryWriteStep
from iris.contracts.memory import (
    MemoryId,
    MemoryQuery,
    MemoryRecord,
    MemorySearchResult,
)
from iris.runtime.wiring.cognitive import (
    CognitiveCycleStores,
    wire_affect_memory_aware_text_response_cognitive_cycle,
    wire_policy_affect_memory_aware_text_response_cognitive_cycle,
)
from iris.runtime.wiring.memory import (
    SQLiteFTS5MemoryRetriever,
    wire_sqlite_hybrid_memory_retriever,
)
from tests.helpers.private_access import get_private_attr_as

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any


def embed_text(text: str) -> tuple[float, float]:
    """Tea / coffee キーワードに基づく 2 次元埋め込み。

    Returns:
        2 次元の決定論的な埋め込み。
    """
    return (
        1.0 if "tea" in text.casefold() else 0.0,
        1.0 if "coffee" in text.casefold() else 0.0,
    )


class _FakeRetriever:
    """テスト用の固定結果レトリーバー。"""

    def __init__(self, results: tuple[MemorySearchResult, ...]) -> None:
        self._results = tuple(results)

    def search(self, query: MemoryQuery) -> tuple[MemorySearchResult, ...]:
        """MemoryQuery を受け取り固定結果を返す。

        Returns:
            初期化時に渡した固定 MemorySearchResult。
        """
        del query
        return self._results


def test_sqlite_hybrid_memory_retriever_wires_vector_and_fts5(
    tmp_path: Path,
) -> None:
    """SQLite store と vector index から hybrid retriever を構成する。"""
    store = SQLiteMemoryStore(tmp_path / "hybrid.db")
    store.put(MemoryRecord(id=MemoryId("m1"), text="green tea"))

    retriever, vector_index = wire_sqlite_hybrid_memory_retriever(
        store=store,
        embed_text=embed_text,
    )

    assert vector_index is not None
    assert retriever.search(MemoryQuery(text="tea", limit=5))


def test_wire_affect_cycle_uses_injected_memory_retriever() -> None:
    """認知サイクル配線が注入された MemoryRetriever を使う。"""
    store = InMemoryMemoryStore()
    fake = _FakeRetriever(
        (
            MemorySearchResult(
                record=MemoryRecord(id=MemoryId("m2"), text="retrieved"),
                score=1.0,
            ),
        ),
    )
    cycle = wire_affect_memory_aware_text_response_cognitive_cycle(
        stores=CognitiveCycleStores(memory_store=store, memory_retriever=fake),
    )

    steps: Any = get_private_attr_as(cycle, "_steps", tuple[object, ...])
    retrieval_steps = [step for step in steps if isinstance(step, MemoryRetrievalStep)]

    assert len(retrieval_steps) == 1
    assert get_private_attr_as(retrieval_steps[0], "_retriever", object) is fake


def test_wire_policy_cycle_passes_vector_index_to_write_step() -> None:
    """vector_index 指定時に MemoryWriteStep に渡される。"""
    store = InMemoryMemoryStore()
    vector_index = InMemoryVectorMemoryIndex(embed_text)
    cycle = wire_policy_affect_memory_aware_text_response_cognitive_cycle(
        stores=CognitiveCycleStores(memory_store=store, vector_index=vector_index),
    )

    steps: Any = get_private_attr_as(cycle, "_steps", tuple[object, ...])
    write_steps = [step for step in steps if isinstance(step, MemoryWriteStep)]

    assert len(write_steps) == 1
    assert get_private_attr_as(write_steps[0], "_vector_index", object) is vector_index


def test_sqlite_fts5_memory_retriever_delegates_to_store(tmp_path: Path) -> None:
    """SQLiteFTS5MemoryRetriever が store.search_fts5 に委譲する。"""
    store = SQLiteMemoryStore(tmp_path / "fts.db")
    store.put(MemoryRecord(id=MemoryId("m1"), text="green tea"))

    retriever = SQLiteFTS5MemoryRetriever(store)
    results = retriever.search(MemoryQuery(text="tea", limit=5))

    assert len(results) >= 1
    assert any(str(result.record.id) == "m1" for result in results)
