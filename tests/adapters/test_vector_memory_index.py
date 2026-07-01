"""InMemoryVectorMemoryIndex のテスト。"""

from __future__ import annotations

import pytest

from iris.adapters.memory.vector_index import InMemoryVectorMemoryIndex
from iris.contracts.memory import (
    MemoryId,
    MemoryKind,
    VectorMemoryEntry,
    VectorMemoryIndexError,
    VectorMemorySearchFilter,
)
from iris.core.ids import ActorId, SpaceId


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


def _entry(memory_id: str, text: str) -> VectorMemoryEntry:
    return VectorMemoryEntry(
        memory_id=MemoryId(memory_id),
        vector=embed_text(text),
        source_digest=text,
        embedding_model="test",
        embedding_dimension=2,
    )


def test_vector_memory_index_search_ranks_by_similarity() -> None:
    """ベクトル類似度でランク付けされた結果を返す。"""
    index = InMemoryVectorMemoryIndex()
    index.upsert(_entry("m1", "User likes coffee."))
    index.upsert(_entry("m2", "User likes tea."))
    index.upsert(_entry("m3", "Tea is served in the afternoon."))

    results = index.search(embed_text("tea"), limit=2)

    assert len(results) == 2
    assert [r.memory_id for r in results] == [MemoryId("m2"), MemoryId("m3")]
    assert [r.score for r in results] == [1.0, 1.0]


def test_vector_memory_index_delete_removes_entry() -> None:
    """Delete でエントリが削除される。"""
    index = InMemoryVectorMemoryIndex()
    index.upsert(_entry("m1", "tea"))

    index.delete(MemoryId("m1"))
    results = index.search(embed_text("tea"), limit=5)

    assert len(results) == 0


def test_vector_memory_index_upsert_updates_existing() -> None:
    """Upsert で既存エントリが更新される。"""
    index = InMemoryVectorMemoryIndex()
    index.upsert(_entry("m1", "coffee"))
    index.upsert(_entry("m1", "tea"))

    results = index.search(embed_text("tea"), limit=5)

    assert len(results) == 1
    assert results[0].memory_id == MemoryId("m1")


def test_vector_memory_index_search_returns_empty_on_zero_limit() -> None:
    """Limit <= 0 で空シーケンスを返す。"""
    index = InMemoryVectorMemoryIndex()
    index.upsert(_entry("m1", "tea"))

    assert tuple(index.search(embed_text("tea"), limit=0)) == ()


def test_vector_memory_index_search_returns_empty_on_no_entries() -> None:
    """エントリなしで空シーケンスを返す。"""
    index = InMemoryVectorMemoryIndex()

    assert tuple(index.search(embed_text("tea"), limit=5)) == ()


def test_vector_memory_index_filters_before_limit() -> None:
    """Out-of-scope entry が上位を埋めても in-scope entry を返す。"""
    index = InMemoryVectorMemoryIndex()
    index.upsert(
        _entry("out-of-scope", "tea").model_copy(
            update={
                "actor_id": ActorId("actor-b"),
                "space_id": SpaceId("space-1"),
                "kind": MemoryKind.PREFERENCE,
            }
        )
    )
    index.upsert(
        _entry("in-scope", "tea").model_copy(
            update={
                "actor_id": ActorId("actor-a"),
                "space_id": SpaceId("space-1"),
                "kind": MemoryKind.PREFERENCE,
            }
        )
    )

    results = index.search(
        embed_text("tea"),
        limit=1,
        filters=VectorMemorySearchFilter(
            actor_id=ActorId("actor-a"),
            space_id=SpaceId("space-1"),
            kind=MemoryKind.PREFERENCE,
        ),
    )

    assert [result.memory_id for result in results] == [MemoryId("in-scope")]


def test_vector_memory_index_excludes_archived_by_filter() -> None:
    """include_archived=False の検索前フィルタで archived entry を除外する。"""
    index = InMemoryVectorMemoryIndex()
    index.upsert(_entry("archived", "tea").model_copy(update={"archived": True}))
    index.upsert(_entry("active", "tea"))

    results = index.search(
        embed_text("tea"),
        limit=5,
        filters=VectorMemorySearchFilter(include_archived=False),
    )

    assert [result.memory_id for result in results] == [MemoryId("active")]


def test_vector_memory_index_dimension_mismatch_uses_index_error() -> None:
    """Dimension mismatch は ValueError ではなく index error に正規化する。"""
    index = InMemoryVectorMemoryIndex()
    with pytest.raises(VectorMemoryIndexError, match="dimension"):
        index.upsert(
            VectorMemoryEntry(
                memory_id=MemoryId("bad"),
                vector=(1.0, 0.0),
                source_digest="bad",
                embedding_model="test",
                embedding_dimension=3,
            )
        )
