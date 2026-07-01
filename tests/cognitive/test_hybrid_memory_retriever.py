"""HybridMemoryRetriever と MemoryReranker のテスト。"""

from __future__ import annotations

from iris.adapters.memory.fake import FakeMemoryStore
from iris.adapters.memory.vector_index import InMemoryVectorMemoryIndex
from iris.cognitive.memory.hybrid import HybridMemoryRetriever, MemoryReranker
from iris.contracts.memory import (
    MemoryId,
    MemoryKind,
    MemoryQuery,
    MemoryRecord,
    MemorySearchResult,
    VectorMemoryEntry,
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


class _Embedding:
    provider = "test"
    model_id = "test"
    dimension = 2

    def embed(self, text: str) -> tuple[float, float]:
        return embed_text(text)

    def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, float], ...]:
        return tuple(self.embed(text) for text in texts)


def _index_for_store(store: FakeMemoryStore) -> InMemoryVectorMemoryIndex:
    index = InMemoryVectorMemoryIndex()
    for result in store.search(MemoryQuery(text="", limit=100, include_archived=True)):
        index.upsert(
            VectorMemoryEntry(
                memory_id=result.record.id,
                vector=embed_text(result.record.text),
                source_digest=result.record.text,
                embedding_provider="test",
                embedding_model="test",
                embedding_dimension=2,
            )
        )
    return index


def _store_with_records() -> FakeMemoryStore:
    return FakeMemoryStore(
        records=(
            MemoryRecord(
                id=MemoryId("m1"),
                text="User likes green tea.",
                salience=0.8,
            ),
            MemoryRecord(
                id=MemoryId("m2"),
                text="User prefers coffee.",
                salience=0.6,
            ),
            MemoryRecord(
                id=MemoryId("m3"),
                text="Tea is calming in the morning.",
                salience=0.9,
            ),
        )
    )


class _FtsRetriever:
    """テスト用の簡易 FTS5 retriever。"""

    def __init__(self, store: FakeMemoryStore) -> None:
        self._store = store

    def search(self, query: MemoryQuery) -> tuple[MemorySearchResult, ...]:
        """検索を実行する。

        Returns:
            tuple[MemorySearchResult, ...]: 検索結果。
        """
        return tuple(self._store.search(query))


def test_hybrid_retriever_combines_fts_and_vector() -> None:
    """ハイブリッド検索が FTS5 とベクトルの結果を統合する。"""
    store = _store_with_records()
    fts = _FtsRetriever(store)
    vector = _index_for_store(store)

    hybrid = HybridMemoryRetriever(
        fts_retriever=fts,
        vector_index=vector,
        embedding=_Embedding(),
        store=store,
        fts_limit=10,
        vector_limit=10,
    )

    results = hybrid.search(MemoryQuery(text="tea", limit=5))
    ids = [str(r.record.id) for r in results]
    assert "m1" in ids
    assert "m3" in ids


def test_hybrid_retriever_respects_limit() -> None:
    """ハイブリッド検索が limit を尊重する。"""
    store = _store_with_records()
    fts = _FtsRetriever(store)
    vector = _index_for_store(store)

    hybrid = HybridMemoryRetriever(
        fts_retriever=fts,
        vector_index=vector,
        embedding=_Embedding(),
        store=store,
    )

    results = hybrid.search(MemoryQuery(text="tea", limit=2))
    assert len(results) <= 2


def test_hybrid_retriever_filters_scope() -> None:
    """ハイブリッド検索が actor_id / space_id でフィルタする。"""
    store = FakeMemoryStore(
        records=(
            MemoryRecord(id=MemoryId("m1"), text="Alice likes tea.", salience=0.8),
            MemoryRecord(id=MemoryId("m2"), text="Bob likes tea.", salience=0.8),
        )
    )
    fts = _FtsRetriever(store)
    vector = _index_for_store(store)

    hybrid = HybridMemoryRetriever(
        fts_retriever=fts,
        vector_index=vector,
        embedding=_Embedding(),
        store=store,
    )

    results = hybrid.search(
        MemoryQuery(text="tea", limit=5, actor_id=ActorId("m1")),
    )
    assert len(results) == 0


def test_hybrid_vector_results_respect_scope_kind_and_archived_filters() -> None:
    """Vector候補にもactor/space/kind/archived filterを適用する。"""
    actor = ActorId("actor-a")
    space = SpaceId("space-a")
    store = FakeMemoryStore(
        records=(
            MemoryRecord(
                id=MemoryId("active"),
                text="active tea",
                actor_id=actor,
                space_id=space,
                kind=MemoryKind.PREFERENCE,
            ),
            MemoryRecord(
                id=MemoryId("archived"),
                text="archived tea",
                actor_id=actor,
                space_id=space,
                kind=MemoryKind.PREFERENCE,
                archived=True,
            ),
            MemoryRecord(
                id=MemoryId("other-space"),
                text="other tea",
                actor_id=actor,
                space_id=SpaceId("space-b"),
                kind=MemoryKind.PREFERENCE,
            ),
            MemoryRecord(
                id=MemoryId("other-kind"),
                text="note tea",
                actor_id=actor,
                space_id=space,
                kind=MemoryKind.NOTE,
            ),
        )
    )
    hybrid = HybridMemoryRetriever(
        fts_retriever=_FtsRetriever(store),
        vector_index=_index_for_store(store),
        embedding=_Embedding(),
        store=store,
    )
    query = MemoryQuery(
        text="tea",
        actor_id=actor,
        space_id=space,
        kind=MemoryKind.PREFERENCE,
        limit=5,
    )

    active_results = hybrid.search(query)
    archived_results = hybrid.search(query.model_copy(update={"include_archived": True}))

    assert [result.record.id for result in active_results] == [MemoryId("active")]
    assert {result.record.id for result in archived_results} == {
        MemoryId("active"),
        MemoryId("archived"),
    }


def test_memory_reranker_composite_score() -> None:
    """MemoryReranker が複合スコアで再ランク付けする。"""
    record1 = MemoryRecord(
        id=MemoryId("m1"),
        text="high salience",
        salience=1.0,
        confidence=1.0,
    )
    record2 = MemoryRecord(
        id=MemoryId("m2"),
        text="low salience",
        salience=0.1,
        confidence=0.1,
    )
    fts_results = (
        MemorySearchResult(record=record1, score=1.0),
        MemorySearchResult(record=record2, score=1.0),
    )
    vector_results: tuple[MemorySearchResult, ...] = ()

    reranker = MemoryReranker()
    results = reranker.rerank(fts_results, vector_results, limit=5)

    assert results[0].record.id == MemoryId("m1")
    assert results[1].record.id == MemoryId("m2")


def test_memory_reranker_boosts_vector_matches() -> None:
    """ベクトル一致が composite score に寄与する。"""
    record = MemoryRecord(
        id=MemoryId("m1"),
        text="match",
        salience=0.5,
        confidence=0.5,
    )
    fts_results = (MemorySearchResult(record=record, score=0.5),)
    vector_results = (MemorySearchResult(record=record, score=1.0),)

    reranker = MemoryReranker(
        fts_weight=0.25,
        vector_weight=0.25,
        salience_weight=0.25,
        confidence_weight=0.25,
    )
    results = reranker.rerank(fts_results, vector_results, limit=5)

    assert len(results) == 1
    assert results[0].score > 0.5


def test_memory_reranker_returns_empty_on_zero_limit() -> None:
    """Limit <= 0 で空シーケンスを返す。"""
    reranker = MemoryReranker()
    assert tuple(reranker.rerank((), (), limit=0)) == ()
