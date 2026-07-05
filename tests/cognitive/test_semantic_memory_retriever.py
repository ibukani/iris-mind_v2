"""SemanticMemoryRetriever の embedding / reranking pipeline tests。"""

from __future__ import annotations

from iris.adapters.memory.fake import FakeMemoryStore
from iris.adapters.memory.vector_index import InMemoryVectorMemoryIndex
from iris.adapters.rerankers.fake import FakeReranker
from iris.cognitive.memory.semantic_retrieval import (
    SemanticMemoryRetrievalDependencies,
    SemanticMemoryRetrievalOptions,
    SemanticMemoryRetriever,
)
from iris.contracts.embeddings import (
    EmbeddingBatchRequest,
    EmbeddingBatchResult,
    EmbeddingRequest,
    EmbeddingResult,
)
from iris.contracts.memory import (
    MemoryId,
    MemoryQuery,
    MemoryRecord,
    MemorySearchResult,
    vector_memory_entry_from_record,
)
from iris.contracts.model_invocation import ModelInvocationMetadata
from iris.contracts.model_policy import ModelCallKind
from iris.contracts.retrieval import (
    RetrievalFallbackReason,
    RetrievalPipelineObservation,
)


class _KeywordEmbedding:
    """テスト用の keyword-based EmbeddingClient。"""

    provider = "test"
    model_id = "keyword-v1"
    dimension = 3

    def __init__(self) -> None:
        """呼び出し回数を記録する。"""
        self.single_calls = 0
        self.batch_calls = 0

    def embed_text(self, request: EmbeddingRequest) -> EmbeddingResult:
        """単一 text を keyword vector に変換する。

        Returns:
            EmbeddingResult: deterministic keyword vector。
        """
        self.single_calls += 1
        return EmbeddingResult(
            vector=self._vector(request.text),
            dimension=self.dimension,
            reason="keyword embedding",
            model_metadata=_embedding_metadata(request.model_slot),
            metadata=request.metadata,
        )

    def embed_text_batch(self, request: EmbeddingBatchRequest) -> EmbeddingBatchResult:
        """複数 text を keyword vector に変換する。

        Returns:
            EmbeddingBatchResult: 入力順の deterministic keyword vectors。
        """
        self.batch_calls += 1
        metadata = _embedding_metadata(request.model_slot)
        return EmbeddingBatchResult(
            embeddings=tuple(
                EmbeddingResult(
                    vector=self._vector(text),
                    dimension=self.dimension,
                    reason="keyword embedding",
                    model_metadata=metadata,
                )
                for text in request.texts
            ),
            reason="keyword embedding batch",
            model_metadata=metadata,
            metadata=request.metadata,
        )

    def _vector(self, text: str) -> tuple[float, float, float]:
        lowered = text.casefold()
        if "mixed" in lowered:
            return (1.0, 1.0, 1.0)
        if "coffee" in lowered:
            return (0.0, 1.0, 0.0)
        if "tea" in lowered or "sencha" in lowered:
            return (1.0, 0.0, 0.0)
        return (0.0, 0.0, 1.0)


class _StoreRetriever:
    """MemoryStore.search を MemoryRetriever として使う。"""

    def __init__(self, store: FakeMemoryStore) -> None:
        """検索対象 store を保持する。"""
        self._store = store

    def search(self, query: MemoryQuery) -> tuple[MemorySearchResult, ...]:
        """Store の検索結果を tuple 化して返す。

        Returns:
            tuple[MemorySearchResult, ...]: 検索結果。
        """
        return tuple(self._store.search(query))


class _RecordingObserver:
    """Raw text を含まない observation を記録する。"""

    def __init__(self) -> None:
        """空の observation list で初期化する。"""
        self.observations: list[RetrievalPipelineObservation] = []

    def record_retrieval(self, observation: RetrievalPipelineObservation) -> None:
        """Observation を保存する。"""
        self.observations.append(observation)


def test_semantic_retriever_gets_memory_candidates_by_embedding_similarity_top_k() -> None:
    """Embedding similarity で memory candidates を top-k 取得する。"""
    records = (
        MemoryRecord(id=MemoryId("tea"), text="User likes green tea."),
        MemoryRecord(id=MemoryId("coffee"), text="User prefers coffee."),
    )
    retriever = _semantic_retriever(records, options=SemanticMemoryRetrievalOptions(fts_limit=0))

    result = retriever.search_with_details(MemoryQuery(text="tea", limit=1))

    assert result.fallback_reason is RetrievalFallbackReason.NONE
    assert [item.source_id for item in result.items] == ["tea"]
    assert result.candidate_count == 2
    assert result.items[0].reason == "fixed fake score"
    assert result.items[0].model_metadata.provider == "fake"


def test_semantic_retriever_uses_reranker_to_narrow_top_k() -> None:
    """Vector candidate top-k を reranker top-k でさらに絞る。"""
    records = (
        MemoryRecord(id=MemoryId("m1"), text="User likes green tea."),
        MemoryRecord(id=MemoryId("m2"), text="User prefers coffee."),
        MemoryRecord(id=MemoryId("m3"), text="User mentioned a notebook."),
    )
    retriever = _semantic_retriever(
        records,
        reranker=FakeReranker({"m2": 0.9, "m1": 0.4, "m3": 0.1}),
        options=SemanticMemoryRetrievalOptions(
            fts_limit=0,
            vector_limit=3,
            candidate_limit=3,
            reranker_limit=1,
            duplicate_similarity_threshold=1.0,
        ),
    )

    result = retriever.search_with_details(MemoryQuery(text="mixed", limit=3))

    assert [item.source_id for item in result.items] == ["m2"]
    assert result.candidate_count == 3
    assert result.selected_count == 1
    assert result.metadata["rerank_reason"] == "fixed fake score rerank"


def test_semantic_retriever_drops_overlapping_memory_by_embedding_similarity() -> None:
    """同一に近い embedding の memory overlap を prompt 候補から除外する。"""
    records = (
        MemoryRecord(id=MemoryId("tea-a"), text="User likes green tea."),
        MemoryRecord(id=MemoryId("tea-b"), text="User likes sencha tea."),
        MemoryRecord(id=MemoryId("coffee"), text="User prefers coffee."),
    )
    retriever = _semantic_retriever(
        records,
        options=SemanticMemoryRetrievalOptions(
            fts_limit=0,
            vector_limit=3,
            candidate_limit=3,
            reranker_limit=3,
            duplicate_similarity_threshold=0.98,
        ),
    )

    result = retriever.search_with_details(MemoryQuery(text="tea", limit=3))

    assert result.dropped_duplicate_count == 1
    assert "tea-a" in {item.source_id for item in result.items}
    assert "tea-b" not in {item.source_id for item in result.items}


def test_semantic_retriever_records_text_free_observability() -> None:
    """Retrieval observability は件数/latency/model metadata を出し raw text は出さない。"""
    observer = _RecordingObserver()
    retriever = _semantic_retriever(
        (MemoryRecord(id=MemoryId("tea"), text="User likes green tea."),),
        observer=observer,
        options=SemanticMemoryRetrievalOptions(fts_limit=0),
    )

    retriever.search_with_details(MemoryQuery(text="secret tea query", limit=1))

    observation = observer.observations[0]
    serialized = observation.model_dump_json()
    assert observation.candidate_count == 1
    assert observation.selected_count == 1
    assert observation.cache_hit_count == 1
    assert observation.embedding_provider == "test"
    assert observation.reranker_provider == "fake"
    assert "secret tea query" not in serialized
    assert "User likes green tea" not in serialized


def test_semantic_retriever_reports_cache_hit_and_miss_counts() -> None:
    """Vector index 有無から embedding cache hit/miss count を観測できる。"""
    records = (
        MemoryRecord(id=MemoryId("indexed"), text="User likes green tea."),
        MemoryRecord(id=MemoryId("lexical-only"), text="User likes tea sweets."),
    )
    store = FakeMemoryStore(records)
    index = InMemoryVectorMemoryIndex()
    embedding = _KeywordEmbedding()
    _upsert(records[0], index, embedding)
    dependencies = SemanticMemoryRetrievalDependencies(
        store=store,
        vector_index=index,
        embedding=embedding,
        reranker=FakeReranker(),
        fts_retriever=_StoreRetriever(store),
    )
    retriever = SemanticMemoryRetriever(
        dependencies,
        options=SemanticMemoryRetrievalOptions(
            fts_limit=10,
            vector_limit=10,
            candidate_limit=10,
            reranker_limit=10,
            duplicate_similarity_threshold=1.0,
        ),
    )

    result = retriever.search_with_details(MemoryQuery(text="tea", limit=10))

    assert result.cache_hit_count == 1
    assert result.cache_miss_count == 1


def test_semantic_retriever_reuses_index_vectors_for_overlap_detection() -> None:
    """Indexed memory は overlap detection でも毎回再 embedding しない。"""
    records = (
        MemoryRecord(id=MemoryId("tea-a"), text="User likes green tea."),
        MemoryRecord(id=MemoryId("coffee"), text="User prefers coffee."),
    )
    store = FakeMemoryStore(records)
    index = InMemoryVectorMemoryIndex()
    embedding = _KeywordEmbedding()
    for record in records:
        _upsert(record, index, embedding)
    dependencies = SemanticMemoryRetrievalDependencies(
        store=store,
        vector_index=index,
        embedding=embedding,
        reranker=FakeReranker(),
    )
    retriever = SemanticMemoryRetriever(
        dependencies,
        options=SemanticMemoryRetrievalOptions(
            fts_limit=0,
            vector_limit=2,
            candidate_limit=2,
            reranker_limit=2,
            duplicate_similarity_threshold=1.0,
        ),
    )
    batch_calls_before = embedding.batch_calls

    result = retriever.search_with_details(MemoryQuery(text="tea", limit=2))

    assert result.cache_hit_count == 2
    assert embedding.batch_calls == batch_calls_before


def test_semantic_retriever_skips_model_calls_when_prompt_budget_selects_zero() -> None:
    """Prompt budget 由来の選択上限 0 では hot-path model call を行わない。"""
    records = (MemoryRecord(id=MemoryId("tea"), text="User likes green tea."),)
    store = FakeMemoryStore(records)
    index = InMemoryVectorMemoryIndex()
    embedding = _KeywordEmbedding()
    _upsert(records[0], index, embedding)
    single_calls_before = embedding.single_calls
    batch_calls_before = embedding.batch_calls
    dependencies = SemanticMemoryRetrievalDependencies(
        store=store,
        vector_index=index,
        embedding=embedding,
        reranker=FakeReranker(),
    )
    retriever = SemanticMemoryRetriever(
        dependencies,
        options=SemanticMemoryRetrievalOptions(reranker_limit=0),
    )

    result = retriever.search_with_details(MemoryQuery(text="tea", limit=5))

    assert result.items == ()
    assert result.candidate_count == 0
    assert result.selected_count == 0
    assert result.fallback_reason is RetrievalFallbackReason.NO_RESULTS
    assert embedding.single_calls == single_calls_before
    assert embedding.batch_calls == batch_calls_before


def test_semantic_retriever_defines_low_score_fallback() -> None:
    """候補はあるが min_score 未満なら low_score fallback を返す。"""
    retriever = _semantic_retriever(
        (MemoryRecord(id=MemoryId("tea"), text="User likes green tea."),),
        reranker=FakeReranker({"tea": 0.1}),
        options=SemanticMemoryRetrievalOptions(fts_limit=0, min_score=0.9),
    )

    result = retriever.search_with_details(MemoryQuery(text="tea", limit=1))

    assert result.items == ()
    assert result.fallback_reason is RetrievalFallbackReason.LOW_SCORE
    assert result.candidate_count == 1


def _semantic_retriever(
    records: tuple[MemoryRecord, ...],
    *,
    reranker: FakeReranker | None = None,
    options: SemanticMemoryRetrievalOptions | None = None,
    observer: _RecordingObserver | None = None,
) -> SemanticMemoryRetriever:
    store = FakeMemoryStore(records)
    index = InMemoryVectorMemoryIndex()
    embedding = _KeywordEmbedding()
    for record in records:
        _upsert(record, index, embedding)
    dependencies = SemanticMemoryRetrievalDependencies(
        store=store,
        vector_index=index,
        embedding=embedding,
        reranker=reranker or FakeReranker(),
    )
    return SemanticMemoryRetriever(dependencies, options=options, observer=observer)


def _upsert(
    record: MemoryRecord,
    index: InMemoryVectorMemoryIndex,
    embedding: _KeywordEmbedding,
) -> None:
    result = embedding.embed_text(EmbeddingRequest(text=record.text, model_slot="memory_rebuild"))
    index.upsert(
        vector_memory_entry_from_record(
            record,
            vector=result.vector,
            embedding_provider=result.model_metadata.provider,
            embedding_model=result.model_metadata.model_name,
            embedding_dimension=result.dimension,
        )
    )


def _embedding_metadata(model_slot: str | None) -> ModelInvocationMetadata:
    return ModelInvocationMetadata(
        call_kind=ModelCallKind.EMBEDDING,
        provider="test",
        model_name="keyword-v1",
        adapter_name="keyword_embedding_test",
        model_slot=model_slot,
    )
