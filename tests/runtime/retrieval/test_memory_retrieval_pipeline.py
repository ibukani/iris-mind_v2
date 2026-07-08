"""Memory retrieval pipeline のテスト。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.adapters.embeddings.fake import DeterministicFakeEmbedding
from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.adapters.memory.vector_index import InMemoryVectorMemoryIndex
from iris.adapters.rerankers.fake import FakeReranker
from iris.contracts.embeddings import embedding_result_with_latency
from iris.contracts.memory import (
    MemoryId,
    MemoryKind,
    MemoryQuery,
    MemoryRecord,
    VectorMemoryEntry,
    VectorMemoryEntryMetadata,
    VectorMemoryIndexError,
    VectorMemorySearchFilter,
    VectorMemorySearchResult,
    vector_memory_entry_from_record,
)
from iris.contracts.prompting import (
    PromptOverflowBehavior,
    PromptProfileName,
    PromptSectionKind,
    PromptTrustBoundary,
)
from iris.contracts.retrieval import (
    RerankRequest,
    RerankResult,
    RetrievalFallbackReason,
    RetrievalSourceKind,
    rerank_result_with_latency,
)
from iris.core.ids import ActorId, SpaceId
from iris.runtime.config.prompt_budget import (
    RuntimePromptBudgetConfig,
    RuntimePromptProfileBudget,
    RuntimePromptSectionBudget,
)
from iris.runtime.prompting.budget import PromptBudgetPolicy
from iris.runtime.retrieval.memory import (
    MemoryRetrievalPipeline,
    MemoryRetrievalPolicy,
    memory_retrieval_policy_for_profile,
)
from iris.runtime.retrieval.overlap import MemoryOverlapDetectionPolicy, detect_memory_overlaps

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.contracts.embeddings import (
        EmbeddingBatchRequest,
        EmbeddingBatchResult,
        EmbeddingRequest,
        EmbeddingResult,
    )


def test_memory_pipeline_uses_embedding_search_reranker_and_prompt_section() -> None:
    """Embedding top-k を reranker で絞り external_context section にする。"""
    embedding = DeterministicFakeEmbedding(dimension=8)
    records = (
        MemoryRecord(id=MemoryId("m1"), text="green tea in the morning"),
        MemoryRecord(id=MemoryId("m2"), text="sencha tea preference"),
        MemoryRecord(id=MemoryId("m3"), text="coffee after lunch"),
    )
    store = _store(*records)
    index = _index_for_records(records, embedding)
    reranker = _SpyReranker({"m2": 0.99, "m1": 0.8, "m3": 0.1})
    pipeline = MemoryRetrievalPipeline(
        store=store,
        vector_index=index,
        embedding_client=embedding,
        reranker=reranker,
        policy=MemoryRetrievalPolicy(
            max_retrieved_candidates=3,
            max_reranked_candidates=2,
            max_prompt_selected_items=1,
        ),
    )

    result = pipeline.retrieve(MemoryQuery(text="tea", limit=5))

    assert [item.source_id for item in result.items] == ["m2"]
    assert result.items[0].source_kind is RetrievalSourceKind.DURABLE_MEMORY
    assert result.items[0].prompt_section_kind is PromptSectionKind.USER_MEMORY
    assert len(result.items[0].model_metadata) == 2
    assert result.prompt_section is not None
    assert result.prompt_section.trust_boundary is PromptTrustBoundary.EXTERNAL_CONTEXT
    assert result.prompt_section.items == ("sencha tea preference",)
    assert result.observability.retrieved_count == 3
    assert result.observability.reranked_count == 1
    assert result.observability.selected_count == 1
    assert reranker.last_request is not None
    assert len(reranker.last_request.candidates) == 2


def test_memory_pipeline_uses_prompt_budget_profile_for_selected_count() -> None:
    """#91 profile budget の max_items を selected item count に接続する。"""
    config = RuntimePromptBudgetConfig()
    policy = memory_retrieval_policy_for_profile(config, PromptProfileName.LOCAL_LOW)

    assert policy.max_prompt_selected_items == 3
    assert policy.max_reranked_candidates == 6
    assert policy.max_retrieved_candidates == 12


def test_memory_pipeline_caches_query_embedding_between_same_queries() -> None:
    """同一 query embedding は pipeline 内 cache hit になり再計算しない。"""
    embedding = _CountingEmbedding(DeterministicFakeEmbedding(dimension=8))
    records = (MemoryRecord(id=MemoryId("m1"), text="green tea"),)
    store = _store(*records)
    index = _index_for_records(records, embedding.delegate)
    pipeline = MemoryRetrievalPipeline(
        store=store,
        vector_index=index,
        embedding_client=embedding,
        reranker=None,
        policy=MemoryRetrievalPolicy(
            max_retrieved_candidates=1,
            max_reranked_candidates=1,
            max_prompt_selected_items=1,
        ),
    )

    first = pipeline.retrieve(MemoryQuery(text="tea", limit=5))
    second = pipeline.retrieve(MemoryQuery(text="tea", limit=5))

    assert embedding.embed_text_calls == 1
    assert first.observability.embedding_cache_hit is False
    assert second.observability.embedding_cache_hit is True


def test_memory_pipeline_does_not_refresh_record_embeddings_on_hot_path() -> None:
    """Retrieval hot path は record embedding batch refresh を実行しない。"""
    embedding = _CountingEmbedding(DeterministicFakeEmbedding(dimension=8))
    records = (
        MemoryRecord(id=MemoryId("m1"), text="fresh green tea"),
        MemoryRecord(id=MemoryId("m2"), text="stale green tea"),
    )
    store = _store(*records)
    index = _index_for_records(records, embedding.delegate)
    pipeline = MemoryRetrievalPipeline(
        store=store,
        vector_index=index,
        embedding_client=embedding,
        reranker=None,
        policy=MemoryRetrievalPolicy(
            max_retrieved_candidates=2,
            max_reranked_candidates=2,
            max_prompt_selected_items=2,
        ),
    )

    result = pipeline.retrieve(MemoryQuery(text="green tea", limit=2))

    assert result.items
    assert embedding.embed_text_calls == 1
    assert embedding.embed_text_batch_calls == 0


def test_memory_pipeline_honors_query_limit_before_provider_calls() -> None:
    """MemoryQuery.limit=0 は provider call なしで no-memory fallback にする。"""
    embedding = _CountingEmbedding(DeterministicFakeEmbedding(dimension=8))
    records = (MemoryRecord(id=MemoryId("m1"), text="green tea"),)
    pipeline = MemoryRetrievalPipeline(
        store=_store(*records),
        vector_index=_index_for_records(records, embedding.delegate),
        embedding_client=embedding,
        reranker=_SpyReranker({"m1": 1.0}),
        policy=MemoryRetrievalPolicy(
            max_retrieved_candidates=5,
            max_reranked_candidates=5,
            max_prompt_selected_items=5,
        ),
    )

    result = pipeline.retrieve(MemoryQuery(text="tea", limit=0))

    assert result.items == ()
    assert result.observability.fallback_reason is RetrievalFallbackReason.QUERY_LIMIT_ZERO
    assert embedding.embed_text_calls == 0


def test_memory_pipeline_falls_back_when_observed_embedding_latency_exceeds_policy() -> None:
    """返却済み embedding result の観測 latency 超過は prompt context に入れない。"""
    embedding = _ObservedLatencyEmbedding(
        DeterministicFakeEmbedding(dimension=8),
        latency_ms=20.0,
    )
    records = (MemoryRecord(id=MemoryId("m1"), text="green tea"),)
    pipeline = MemoryRetrievalPipeline(
        store=_store(*records),
        vector_index=_index_for_records(records, embedding.delegate),
        embedding_client=embedding,
        reranker=None,
        policy=MemoryRetrievalPolicy(
            max_retrieved_candidates=1,
            max_reranked_candidates=1,
            max_prompt_selected_items=1,
            max_observed_embedding_latency_ms=10.0,
        ),
    )

    result = pipeline.retrieve(MemoryQuery(text="tea", limit=5))

    assert result.items == ()
    assert result.observability.fallback_reason is RetrievalFallbackReason.EMBEDDING_TIMEOUT
    assert 19.9 < result.observability.embedding_latency_ms < 20.1


def test_memory_pipeline_clamps_retrieval_rerank_and_selection_to_query_limit() -> None:
    """MemoryQuery.limit は retrieved/reranked/selected の上限として働く。"""
    embedding = DeterministicFakeEmbedding(dimension=8)
    records = (
        MemoryRecord(id=MemoryId("m1"), text="green tea"),
        MemoryRecord(id=MemoryId("m2"), text="sencha tea"),
        MemoryRecord(id=MemoryId("m3"), text="black tea"),
    )
    reranker = _SpyReranker({"m1": 0.7, "m2": 0.9, "m3": 0.8})
    pipeline = MemoryRetrievalPipeline(
        store=_store(*records),
        vector_index=_index_for_records(records, embedding),
        embedding_client=embedding,
        reranker=reranker,
        policy=MemoryRetrievalPolicy(
            max_retrieved_candidates=5,
            max_reranked_candidates=5,
            max_prompt_selected_items=5,
        ),
    )

    result = pipeline.retrieve(MemoryQuery(text="tea", limit=1))

    assert len(result.items) == 1
    assert result.observability.retrieved_count == 1
    assert result.observability.reranked_count == 1
    assert reranker.last_request is not None
    assert len(reranker.last_request.candidates) == 1
    assert reranker.last_request.limit == 1


def test_memory_pipeline_converts_vector_index_failure_to_no_memory_fallback() -> None:
    """Vector index failure は hot path から例外を漏らさない。"""
    embedding = DeterministicFakeEmbedding(dimension=8)
    records = (MemoryRecord(id=MemoryId("m1"), text="green tea"),)
    pipeline = MemoryRetrievalPipeline(
        store=_store(*records),
        vector_index=_FailingVectorIndex(),
        embedding_client=embedding,
        reranker=None,
        policy=MemoryRetrievalPolicy(
            max_retrieved_candidates=5,
            max_reranked_candidates=5,
            max_prompt_selected_items=5,
        ),
    )

    result = pipeline.retrieve(MemoryQuery(text="tea", limit=5))

    assert result.items == ()
    assert result.observability.fallback_reason is RetrievalFallbackReason.VECTOR_INDEX_UNAVAILABLE


def test_memory_pipeline_falls_back_when_observed_reranker_latency_exceeds_policy() -> None:
    """返却済み rerank result の観測 latency 超過は prompt context に入れない。"""
    embedding = DeterministicFakeEmbedding(dimension=8)
    records = (MemoryRecord(id=MemoryId("m1"), text="green tea"),)
    pipeline = MemoryRetrievalPipeline(
        store=_store(*records),
        vector_index=_index_for_records(records, embedding),
        embedding_client=embedding,
        reranker=_ObservedLatencyReranker(_SpyReranker({"m1": 1.0}), latency_ms=20.0),
        policy=MemoryRetrievalPolicy(
            max_retrieved_candidates=1,
            max_reranked_candidates=1,
            max_prompt_selected_items=1,
            max_observed_reranker_latency_ms=10.0,
        ),
    )

    result = pipeline.retrieve(MemoryQuery(text="tea", limit=5))

    assert result.items == ()
    assert result.prompt_section is None
    assert result.observability.retrieved_count == 1
    assert 19.9 < result.observability.reranking_latency_ms < 20.1
    assert result.observability.fallback_reason is RetrievalFallbackReason.RERANKER_TIMEOUT


def test_memory_pipeline_falls_back_to_vector_results_when_reranker_unavailable() -> None:
    """Reranker failure は deterministic に vector result を prompt 候補へ戻す。"""
    embedding = DeterministicFakeEmbedding(dimension=8)
    records = (MemoryRecord(id=MemoryId("m1"), text="green tea"),)
    store = _store(*records)
    index = _index_for_records(records, embedding)
    pipeline = MemoryRetrievalPipeline(
        store=store,
        vector_index=index,
        embedding_client=embedding,
        reranker=_FailingReranker(),
        policy=MemoryRetrievalPolicy(
            max_retrieved_candidates=1,
            max_reranked_candidates=1,
            max_prompt_selected_items=1,
        ),
    )

    result = pipeline.retrieve(MemoryQuery(text="tea", limit=5))

    assert [item.source_id for item in result.items] == ["m1"]
    assert result.observability.fallback_reason is RetrievalFallbackReason.RERANKER_UNAVAILABLE


def test_memory_pipeline_filters_low_scores_when_reranker_unavailable() -> None:
    """Reranker unavailable 経路でも min_score 未満は prompt に載せない。"""
    embedding = DeterministicFakeEmbedding(dimension=8)
    records = (MemoryRecord(id=MemoryId("m1"), text="green tea"),)
    store = _store(*records)
    index = _index_for_records(records, embedding)
    pipeline = MemoryRetrievalPipeline(
        store=store,
        vector_index=index,
        embedding_client=embedding,
        reranker=_FailingReranker(),
        policy=MemoryRetrievalPolicy(
            max_retrieved_candidates=1,
            max_reranked_candidates=1,
            max_prompt_selected_items=1,
            min_score=2.0,
        ),
    )

    result = pipeline.retrieve(MemoryQuery(text="tea", limit=5))

    assert result.items == ()
    assert result.prompt_section is None
    assert result.observability.fallback_reason is RetrievalFallbackReason.LOW_SCORE


def test_memory_pipeline_keeps_scope_and_source_boundaries() -> None:
    """Durable memory だけを source とし、actor/space/kind/archive scope を守る。"""
    actor = ActorId("actor-a")
    space = SpaceId("space-a")
    embedding = DeterministicFakeEmbedding(dimension=8)
    records = (
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
        MemoryRecord(id=MemoryId("other"), text="other tea", space_id=SpaceId("space-b")),
    )
    store = _store(*records)
    pipeline = MemoryRetrievalPipeline(
        store=store,
        vector_index=_index_for_records(records, embedding),
        embedding_client=embedding,
        reranker=None,
        policy=MemoryRetrievalPolicy(
            max_retrieved_candidates=5,
            max_reranked_candidates=5,
            max_prompt_selected_items=5,
        ),
    )

    result = pipeline.retrieve(
        MemoryQuery(
            text="tea",
            actor_id=actor,
            space_id=space,
            kind=MemoryKind.PREFERENCE,
            limit=5,
        )
    )

    assert [item.source_id for item in result.items] == ["active"]
    assert {item.source_kind for item in result.items} == {RetrievalSourceKind.DURABLE_MEMORY}


def test_memory_pipeline_prompt_section_is_bounded_by_prompt_budget_policy() -> None:
    """Retrieval result は #91 PromptBudgetPolicy で overflow 処理できる。"""
    embedding = DeterministicFakeEmbedding(dimension=8)
    long_text = "tea " * 50
    records = (MemoryRecord(id=MemoryId("m1"), text=long_text),)
    store = _store(*records)
    pipeline = MemoryRetrievalPipeline(
        store=store,
        vector_index=_index_for_records(records, embedding),
        embedding_client=embedding,
        reranker=None,
        policy=MemoryRetrievalPolicy(
            max_retrieved_candidates=1,
            max_reranked_candidates=1,
            max_prompt_selected_items=1,
        ),
    )
    section = pipeline.retrieve(MemoryQuery(text="tea", limit=5)).prompt_section
    assert section is not None
    budget = _single_memory_profile(max_chars=40, max_items=1)

    result = PromptBudgetPolicy(PromptProfileName.LOCAL_LOW, budget).apply((section,))

    report = result.report.section_reports[0]
    assert report.kind is PromptSectionKind.USER_MEMORY
    assert report.trust_boundary is PromptTrustBoundary.EXTERNAL_CONTEXT
    assert report.output_items == 1
    assert report.truncated_chars > 0


def test_memory_overlap_detection_uses_embedding_similarity_and_bounds_candidates() -> None:
    """Embedding similarity で重複候補を検出し、candidate count を bounded にする。"""
    embedding = _CountingEmbedding(DeterministicFakeEmbedding(dimension=8))
    records = (
        MemoryRecord(id=MemoryId("m1"), text="green tea"),
        MemoryRecord(id=MemoryId("m2"), text="green tea"),
        MemoryRecord(id=MemoryId("m3"), text="coffee"),
    )

    overlaps = detect_memory_overlaps(
        records,
        embedding,
        MemoryOverlapDetectionPolicy(max_candidates=2, similarity_threshold=0.99),
    )

    assert [(item.left_source_id, item.right_source_id) for item in overlaps] == [("m1", "m2")]
    assert overlaps[0].source_kind is RetrievalSourceKind.DURABLE_MEMORY
    assert embedding.last_batch_texts == ("green tea", "green tea")


class _CountingEmbedding:
    def __init__(self, delegate: DeterministicFakeEmbedding) -> None:
        self.delegate = delegate
        self.embed_text_calls = 0
        self.embed_text_batch_calls = 0
        self.last_batch_texts: tuple[str, ...] = ()

    @property
    def provider(self) -> str:
        return self.delegate.provider

    @property
    def model_id(self) -> str:
        return self.delegate.model_id

    @property
    def dimension(self) -> int:
        return self.delegate.dimension

    def embed_text(self, request: EmbeddingRequest) -> EmbeddingResult:
        self.embed_text_calls += 1
        return self.delegate.embed_text(request)

    def embed_text_batch(self, request: EmbeddingBatchRequest) -> EmbeddingBatchResult:
        self.embed_text_batch_calls += 1
        self.last_batch_texts = request.texts
        return self.delegate.embed_text_batch(request)


class _ObservedLatencyEmbedding:
    def __init__(self, delegate: DeterministicFakeEmbedding, *, latency_ms: float) -> None:
        self.delegate = delegate
        self._latency_ms = latency_ms

    @property
    def provider(self) -> str:
        return self.delegate.provider

    @property
    def model_id(self) -> str:
        return self.delegate.model_id

    @property
    def dimension(self) -> int:
        return self.delegate.dimension

    def embed_text(self, request: EmbeddingRequest) -> EmbeddingResult:
        return embedding_result_with_latency(
            self.delegate.embed_text(request),
            latency_ms=self._latency_ms,
        )

    def embed_text_batch(self, request: EmbeddingBatchRequest) -> EmbeddingBatchResult:
        return self.delegate.embed_text_batch(request)


class _SpyReranker:
    def __init__(self, scores: dict[str, float]) -> None:
        self._delegate = FakeReranker(scores)
        self.last_request: RerankRequest | None = None

    def rerank(self, request: RerankRequest) -> RerankResult:
        self.last_request = request
        return self._delegate.rerank(request)


class _ObservedLatencyReranker:
    def __init__(self, delegate: _SpyReranker, *, latency_ms: float) -> None:
        self._delegate = delegate
        self._latency_ms = latency_ms

    def rerank(self, request: RerankRequest) -> RerankResult:
        return rerank_result_with_latency(
            self._delegate.rerank(request),
            latency_ms=self._latency_ms,
        )


class _FailingReranker:
    def rerank(self, request: RerankRequest) -> RerankResult:
        raise RuntimeError(request.query)


class _FailingVectorIndex:
    def upsert(self, entry: VectorMemoryEntry) -> None:
        raise VectorMemoryIndexError(str(entry.memory_id))

    def delete(self, memory_id: MemoryId) -> None:
        raise VectorMemoryIndexError(str(memory_id))

    def search(
        self,
        query_vector: Sequence[float],
        *,
        limit: int,
        filters: VectorMemorySearchFilter | None = None,
    ) -> tuple[VectorMemorySearchResult, ...]:
        raise VectorMemoryIndexError(str((len(query_vector), limit, filters)))

    def metadata(self, memory_id: MemoryId) -> VectorMemoryEntryMetadata | None:
        raise VectorMemoryIndexError(str(memory_id))

    def ids(self) -> tuple[MemoryId, ...]:
        return ()


def _store(*records: MemoryRecord) -> InMemoryMemoryStore:
    store = InMemoryMemoryStore()
    for record in records:
        store.put(record)
    return store


def _index_for_records(
    records: tuple[MemoryRecord, ...],
    embedding: DeterministicFakeEmbedding,
) -> InMemoryVectorMemoryIndex:
    index = InMemoryVectorMemoryIndex()
    for record in records:
        index.upsert(
            vector_memory_entry_from_record(
                record,
                vector=embedding.embed(record.text),
                embedding_provider=embedding.provider,
                embedding_model=embedding.model_id,
                embedding_dimension=embedding.dimension,
            )
        )
    return index


def _single_memory_profile(*, max_chars: int, max_items: int) -> RuntimePromptProfileBudget:
    section = RuntimePromptSectionBudget(
        max_chars=max_chars,
        max_items=max_items,
        priority=50,
        overflow_behavior=PromptOverflowBehavior.TRUNCATE_ITEMS,
    )
    required = RuntimePromptSectionBudget(
        max_chars=1,
        max_items=1,
        priority=100,
        overflow_behavior=PromptOverflowBehavior.REQUIRED,
    )
    return RuntimePromptProfileBudget(
        total_max_chars=max_chars,
        system=required,
        persona=section,
        safety_constraints=required,
        recent_conversation=section,
        user_memory=section,
        project_memory=section,
        relationship_signal=section,
        internal_state=section,
        interaction_policy=section,
        task_context=section,
        user_input=required,
    )
