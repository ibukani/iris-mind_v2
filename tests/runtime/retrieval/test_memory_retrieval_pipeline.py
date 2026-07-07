"""Memory retrieval pipeline のテスト。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.adapters.embeddings.fake import DeterministicFakeEmbedding
from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.adapters.memory.vector_index import InMemoryVectorMemoryIndex
from iris.adapters.rerankers.fake import FakeReranker
from iris.contracts.memory import (
    MemoryId,
    MemoryKind,
    MemoryQuery,
    MemoryRecord,
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


def test_memory_pipeline_timeout_returns_no_memory_without_breaking_response_path() -> None:
    """Embedding / reranker timeout は例外を漏らさず no memory fallback にする。"""
    embedding = DeterministicFakeEmbedding(dimension=8)
    records = (MemoryRecord(id=MemoryId("m1"), text="green tea"),)
    store = _store(*records)
    index = _index_for_records(records, embedding)
    embedding_timeout = MemoryRetrievalPipeline(
        store=store,
        vector_index=index,
        embedding_client=embedding,
        reranker=None,
        policy=MemoryRetrievalPolicy(
            max_retrieved_candidates=1,
            max_reranked_candidates=1,
            max_prompt_selected_items=1,
            embedding_timeout_ms=1.0,
        ),
        clock=_StepClock((0.0, 0.01)),
    )
    reranker_timeout = MemoryRetrievalPipeline(
        store=store,
        vector_index=index,
        embedding_client=embedding,
        reranker=FakeReranker({"m1": 1.0}),
        policy=MemoryRetrievalPolicy(
            max_retrieved_candidates=1,
            max_reranked_candidates=1,
            max_prompt_selected_items=1,
            reranker_timeout_ms=1.0,
        ),
        clock=_StepClock((0.0, 0.0, 0.0, 0.01)),
    )

    embedding_result = embedding_timeout.retrieve(MemoryQuery(text="tea", limit=5))
    reranker_result = reranker_timeout.retrieve(MemoryQuery(text="tea", limit=5))

    assert embedding_result.items == ()
    assert (
        embedding_result.observability.fallback_reason is RetrievalFallbackReason.EMBEDDING_TIMEOUT
    )
    assert reranker_result.items == ()
    assert reranker_result.observability.fallback_reason is RetrievalFallbackReason.RERANKER_TIMEOUT


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
        self.last_batch_texts = request.texts
        return self.delegate.embed_text_batch(request)


class _SpyReranker:
    def __init__(self, scores: dict[str, float]) -> None:
        self._delegate = FakeReranker(scores)
        self.last_request: RerankRequest | None = None

    def rerank(self, request: RerankRequest) -> RerankResult:
        self.last_request = request
        return self._delegate.rerank(request)


class _FailingReranker:
    def rerank(self, request: RerankRequest) -> RerankResult:
        raise RuntimeError(request.query)


@dataclass
class _StepClock:
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        self._index = 0

    def __call__(self) -> float:
        if self._index >= len(self.values):
            return self.values[-1]
        value = self.values[self._index]
        self._index += 1
        return value


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
