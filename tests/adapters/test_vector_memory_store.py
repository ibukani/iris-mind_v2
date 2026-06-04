"""決定論的埋め込みを使用したInMemoryVectorMemoryStoreのテスト。"""

from __future__ import annotations

import pytest

from iris.adapters.memory.vector import InMemoryVectorMemoryStore
from iris.contracts.memory import MemoryId, MemoryQuery, MemoryRecord
from iris.core.ids import ActorId


def embed_text(text: str) -> tuple[float, float]:
    """teaおよびcoffeeキーワードの存在に基づいて2次元埋め込みを返す。

    Returns:
        tuple[float, float]: 埋め込みベクトル。
    """
    return (
        1.0 if "tea" in text.casefold() else 0.0,
        1.0 if "coffee" in text.casefold() else 0.0,
    )


def test_in_memory_vector_store_search_is_deterministic() -> None:
    """ベクトル検索が類似度でランク付けされた決定論的な結果を返すことを確認する。"""
    store = InMemoryVectorMemoryStore(
        embed_text,
        records=(
            MemoryRecord(id=MemoryId("m1"), text="User likes coffee."),
            MemoryRecord(id=MemoryId("m2"), text="User likes tea."),
            MemoryRecord(id=MemoryId("m3"), text="Tea is served in the afternoon."),
        ),
    )

    results = store.search(MemoryQuery(text="tea", limit=2))

    assert [result.record.id for result in results] == [MemoryId("m2"), MemoryId("m3")]
    assert [result.score for result in results] == [1.0, 1.0]


def test_in_memory_vector_store_filters_subject_id() -> None:
    """ベクトル検索がsubject_idで結果をフィルタリングすることを確認する。"""
    actor_id = ActorId("actor-1")
    store = InMemoryVectorMemoryStore(
        embed_text,
        records=(
            MemoryRecord(id=MemoryId("m1"), text="User likes tea.", subject_id=actor_id),
            MemoryRecord(id=MemoryId("m2"), text="Someone else likes tea."),
        ),
    )

    results = store.search(MemoryQuery(text="tea", subject_id=actor_id))

    assert [result.record.id for result in results] == [MemoryId("m1")]


def test_in_memory_vector_store_rejects_unstable_embedding_dimensions() -> None:
    """埋め込み次元が変化したときにベクターストアがValueErrorを発生させることを確認する。"""

    def unstable_embed(text: str) -> tuple[float, ...]:
        if text == "query":
            return (1.0,)
        return (1.0, 0.0)

    store = InMemoryVectorMemoryStore(
        unstable_embed,
        records=(MemoryRecord(id=MemoryId("m1"), text="record"),),
    )

    with pytest.raises(ValueError, match="stable dimensions"):
        store.search(MemoryQuery(text="query"))
