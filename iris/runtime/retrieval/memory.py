"""Prompt budget に接続する bounded memory retrieval pipeline。"""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import TYPE_CHECKING

from iris.contracts.embeddings import EmbeddingRequest, EmbeddingResult
from iris.contracts.memory import (
    MemoryQuery,
    MemoryRecord,
    MemorySearchResult,
    VectorMemoryIndexError,
    VectorMemorySearchFilter,
)
from iris.contracts.prompting import PromptSectionInput, PromptSectionKind, PromptTrustBoundary
from iris.contracts.retrieval import (
    RerankCandidate,
    RerankRequest,
    RerankResult,
    RetrievalFallbackReason,
    RetrievalObservability,
    RetrievalPipelineResult,
    RetrievalSourceKind,
    RetrievedContextItem,
)
from iris.runtime.config.prompt_budget import (
    RuntimePromptBudgetConfig,
    memory_top_k_for_profile,
    project_context_top_k_for_profile,
)

if TYPE_CHECKING:
    from iris.contracts.embeddings import EmbeddingClient
    from iris.contracts.memory import MemoryStore, VectorMemoryIndex
    from iris.contracts.prompting import PromptProfileName
    from iris.contracts.retrieval import Reranker


@dataclass(frozen=True)
class MemoryRetrievalPolicy:
    """Hot path retrieval の上限と観測済み latency fallback policy。"""

    max_retrieved_candidates: int
    max_reranked_candidates: int
    max_prompt_selected_items: int
    max_observed_embedding_latency_ms: float = 250.0
    max_observed_reranker_latency_ms: float = 250.0
    min_score: float = 0.0
    prompt_section_kind: PromptSectionKind = PromptSectionKind.USER_MEMORY
    prompt_title: str = "Relevant memories"
    model_slot: str | None = "memory_retrieval"

    def __post_init__(self) -> None:
        """Policy の hot path 上限を検証する。

        Raises:
            ValueError: 上限または観測済み latency 閾値が負の値の場合。
        """
        if self.max_retrieved_candidates < 0:
            msg = "max_retrieved_candidates must be >= 0"
            raise ValueError(msg)
        if self.max_reranked_candidates < 0:
            msg = "max_reranked_candidates must be >= 0"
            raise ValueError(msg)
        if self.max_prompt_selected_items < 0:
            msg = "max_prompt_selected_items must be >= 0"
            raise ValueError(msg)
        if self.max_observed_embedding_latency_ms < 0:
            msg = "max_observed_embedding_latency_ms must be >= 0"
            raise ValueError(msg)
        if self.max_observed_reranker_latency_ms < 0:
            msg = "max_observed_reranker_latency_ms must be >= 0"
            raise ValueError(msg)


class MemoryRetrievalPipeline:
    """Embedding search、reranking、prompt section selection を束ねる。"""

    def __init__(
        self,
        *,
        store: MemoryStore,
        vector_index: VectorMemoryIndex,
        embedding_client: EmbeddingClient,
        reranker: Reranker | None,
        policy: MemoryRetrievalPolicy,
    ) -> None:
        """依存 port と retrieval policy を注入する。"""
        self._store = store
        self._vector_index = vector_index
        self._embedding_client = embedding_client
        self._reranker = reranker
        self._policy = policy
        self._query_embedding_cache: dict[_EmbeddingCacheKey, EmbeddingResult] = {}

    def retrieve(self, query: MemoryQuery) -> RetrievalPipelineResult:
        """MemoryQuery から prompt-safe な retrieval result を返す。

        Args:
            query: actor / space / kind scope を含む memory query。

        Returns:
            selected items、prompt section、観測 metadata。
        """
        result: RetrievalPipelineResult
        if not query.text.strip():
            result = _empty_result(RetrievalFallbackReason.EMPTY_QUERY)
        elif query.limit <= 0:
            result = _empty_result(RetrievalFallbackReason.QUERY_LIMIT_ZERO)
        elif self._policy.max_prompt_selected_items == 0:
            result = _empty_result(RetrievalFallbackReason.PROMPT_BUDGET_ZERO)
        else:
            result = self._retrieve_with_prompt_budget(query)
        return result

    def _retrieve_with_prompt_budget(self, query: MemoryQuery) -> RetrievalPipelineResult:
        limits = _limits_for_query(self._policy, query)
        embedding = self._embed_query(query.text)
        if embedding.result is None:
            return _empty_result(
                embedding.fallback_reason,
                embedding_latency_ms=embedding.latency_ms,
                embedding_cache_hit=embedding.cache_hit,
            )
        return self._retrieve_with_embedding(query, limits, embedding, embedding.result)

    def _retrieve_with_embedding(
        self,
        query: MemoryQuery,
        limits: _RetrievalLimits,
        embedding: _EmbeddingOutcome,
        embedding_result: EmbeddingResult,
    ) -> RetrievalPipelineResult:
        try:
            retrieved = self._retrieve_vector_candidates(query, embedding_result, limits)
        except VectorMemoryIndexError:
            return _empty_result(
                RetrievalFallbackReason.VECTOR_INDEX_UNAVAILABLE,
                embedding_latency_ms=embedding.latency_ms,
                embedding_cache_hit=embedding.cache_hit,
            )
        if not retrieved:
            return _empty_result(
                RetrievalFallbackReason.EMPTY_INDEX,
                embedding_latency_ms=embedding.latency_ms,
                embedding_cache_hit=embedding.cache_hit,
            )

        reranked = self._rerank(query.text, retrieved, limits)
        if reranked.fallback_reason is RetrievalFallbackReason.RERANKER_TIMEOUT:
            return _empty_result(
                RetrievalFallbackReason.RERANKER_TIMEOUT,
                retrieved_count=len(retrieved),
                embedding_latency_ms=embedding.latency_ms,
                reranking_latency_ms=reranked.latency_ms,
                embedding_cache_hit=embedding.cache_hit,
            )
        selected = self._select_items(retrieved, reranked.result, embedding_result, limits)
        fallback = RetrievalFallbackReason.LOW_SCORE if not selected else None
        return RetrievalPipelineResult(
            items=selected,
            prompt_section=_prompt_section(self._policy, selected),
            observability=RetrievalObservability(
                retrieved_count=len(retrieved),
                reranked_count=_reranked_count(reranked.result),
                selected_count=len(selected),
                embedding_latency_ms=embedding.latency_ms,
                reranking_latency_ms=reranked.latency_ms,
                embedding_cache_hit=embedding.cache_hit,
                fallback_reason=fallback or reranked.fallback_reason,
            ),
        )

    def _embed_query(self, text: str) -> _EmbeddingOutcome:
        key = _EmbeddingCacheKey(
            provider=self._embedding_client.provider,
            model_id=self._embedding_client.model_id,
            dimension=self._embedding_client.dimension,
            model_slot=self._policy.model_slot,
            text=text,
        )
        cached = self._query_embedding_cache.get(key)
        if cached is not None:
            return _EmbeddingOutcome(result=cached, latency_ms=0.0, cache_hit=True)
        return self._embed_query_uncached(text, key)

    def _embed_query_uncached(
        self,
        text: str,
        key: _EmbeddingCacheKey,
    ) -> _EmbeddingOutcome:
        started = time.monotonic()
        try:
            result = self._embedding_client.embed_text(
                EmbeddingRequest(
                    text=text,
                    model_slot=self._policy.model_slot,
                    metadata={"stage": "memory_retrieval_query"},
                )
            )
        except (RuntimeError, ValueError) as exc:
            return _EmbeddingOutcome(
                result=None,
                latency_ms=_elapsed_ms(started),
                cache_hit=False,
                fallback_reason=RetrievalFallbackReason.EMBEDDING_UNAVAILABLE,
                error_message=str(exc),
            )
        latency_ms = result.latency_ms or _elapsed_ms(started)
        if latency_ms > self._policy.max_observed_embedding_latency_ms:
            return _EmbeddingOutcome(
                result=None,
                latency_ms=latency_ms,
                cache_hit=False,
                fallback_reason=RetrievalFallbackReason.EMBEDDING_TIMEOUT,
            )
        self._query_embedding_cache[key] = result
        return _EmbeddingOutcome(result=result, latency_ms=latency_ms, cache_hit=False)

    def _retrieve_vector_candidates(
        self,
        query: MemoryQuery,
        embedding: EmbeddingResult,
        limits: _RetrievalLimits,
    ) -> tuple[MemorySearchResult, ...]:
        if limits.max_retrieved_candidates == 0:
            return ()
        raw = self._vector_index.search(
            embedding.vector,
            limit=limits.max_retrieved_candidates,
            filters=VectorMemorySearchFilter(
                actor_id=query.actor_id,
                space_id=query.space_id,
                kind=query.kind,
                include_archived=query.include_archived,
            ),
        )
        results: list[MemorySearchResult] = []
        for item in raw:
            record = self._store.get(item.memory_id)
            if record is None or _record_is_out_of_scope(record, query):
                continue
            results.append(MemorySearchResult(record=record, score=item.score))
        return tuple(results)

    def _rerank(
        self,
        query_text: str,
        candidates: tuple[MemorySearchResult, ...],
        limits: _RetrievalLimits,
    ) -> _RerankOutcome:
        if self._reranker is None:
            return _RerankOutcome(
                result=None,
                latency_ms=0.0,
                fallback_reason=RetrievalFallbackReason.RERANKER_UNAVAILABLE,
            )
        reranker = self._reranker
        started = time.monotonic()
        try:
            result = reranker.rerank(
                RerankRequest(
                    query=query_text,
                    candidates=tuple(
                        RerankCandidate(
                            candidate_id=str(candidate.record.id),
                            text=candidate.record.text,
                            base_score=candidate.score,
                            metadata=candidate.record.metadata,
                        )
                        for candidate in candidates[: limits.max_reranked_candidates]
                    ),
                    limit=limits.max_prompt_selected_items,
                    model_slot=self._policy.model_slot,
                    metadata={"stage": "memory_retrieval_rerank"},
                ),
            )
        except (RuntimeError, ValueError) as exc:
            return _RerankOutcome(
                result=None,
                latency_ms=_elapsed_ms(started),
                fallback_reason=RetrievalFallbackReason.RERANKER_UNAVAILABLE,
                error_message=str(exc),
            )
        latency_ms = result.latency_ms or _elapsed_ms(started)
        if latency_ms > self._policy.max_observed_reranker_latency_ms:
            return _RerankOutcome(
                result=None,
                latency_ms=latency_ms,
                fallback_reason=RetrievalFallbackReason.RERANKER_TIMEOUT,
            )
        return _RerankOutcome(result=result, latency_ms=latency_ms)

    def _select_items(
        self,
        retrieved: tuple[MemorySearchResult, ...],
        reranked: RerankResult | None,
        embedding: EmbeddingResult,
        limits: _RetrievalLimits,
    ) -> tuple[RetrievedContextItem, ...]:
        if reranked is None:
            ranked = tuple(item for item in retrieved if item.score >= self._policy.min_score)[
                : limits.max_prompt_selected_items
            ]
            return tuple(_item_from_vector_result(self._policy, item, embedding) for item in ranked)
        by_id = {str(item.record.id): item for item in retrieved}
        selected: list[RetrievedContextItem] = []
        for item in reranked.items:
            memory = by_id.get(item.candidate.candidate_id)
            if memory is None or item.score < self._policy.min_score:
                continue
            selected.append(
                RetrievedContextItem(
                    source_id=item.candidate.candidate_id,
                    source_kind=RetrievalSourceKind.DURABLE_MEMORY,
                    prompt_section_kind=self._policy.prompt_section_kind,
                    text=memory.record.text,
                    score=item.score,
                    reason=item.reason,
                    model_metadata=(embedding.model_metadata, item.model_metadata),
                    metadata=memory.record.metadata,
                )
            )
        return tuple(selected[: limits.max_prompt_selected_items])


def memory_retrieval_policy_for_profile(
    config: RuntimePromptBudgetConfig,
    profile: PromptProfileName,
    *,
    section: PromptSectionKind = PromptSectionKind.USER_MEMORY,
    candidate_multiplier: int = 4,
    rerank_multiplier: int = 2,
) -> MemoryRetrievalPolicy:
    """Prompt budget profile から bounded retrieval policy を作る。

    Returns:
        prompt section の max_items を selected item 上限に使う policy。
    """
    selected = _selected_item_limit(config, profile, section)
    return MemoryRetrievalPolicy(
        max_retrieved_candidates=selected * candidate_multiplier,
        max_reranked_candidates=selected * rerank_multiplier,
        max_prompt_selected_items=selected,
        prompt_section_kind=section,
        prompt_title=_prompt_title(section),
    )


@dataclass(frozen=True)
class _EmbeddingCacheKey:
    provider: str
    model_id: str
    dimension: int
    model_slot: str | None
    text: str


@dataclass(frozen=True)
class _EmbeddingOutcome:
    result: EmbeddingResult | None
    latency_ms: float
    cache_hit: bool
    fallback_reason: RetrievalFallbackReason | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class _RerankOutcome:
    result: RerankResult | None
    latency_ms: float
    fallback_reason: RetrievalFallbackReason | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class _RetrievalLimits:
    max_retrieved_candidates: int
    max_reranked_candidates: int
    max_prompt_selected_items: int


def _limits_for_query(policy: MemoryRetrievalPolicy, query: MemoryQuery) -> _RetrievalLimits:
    query_limit = max(query.limit, 0)
    return _RetrievalLimits(
        max_retrieved_candidates=min(policy.max_retrieved_candidates, query_limit),
        max_reranked_candidates=min(policy.max_reranked_candidates, query_limit),
        max_prompt_selected_items=min(policy.max_prompt_selected_items, query_limit),
    )


def _selected_item_limit(
    config: RuntimePromptBudgetConfig,
    profile: PromptProfileName,
    section: PromptSectionKind,
) -> int:
    if section is PromptSectionKind.USER_MEMORY:
        return memory_top_k_for_profile(config, profile)
    if section is PromptSectionKind.PROJECT_MEMORY:
        return project_context_top_k_for_profile(config, profile)
    return config.profile_budget(profile).section_budget(section).max_items


def _prompt_title(section: PromptSectionKind) -> str:
    if section is PromptSectionKind.PROJECT_MEMORY:
        return "Relevant project context"
    if section is PromptSectionKind.TASK_CONTEXT:
        return "Relevant task context"
    return "Relevant memories"


def _record_is_out_of_scope(record: MemoryRecord, query: MemoryQuery) -> bool:
    return (
        (not query.include_archived and record.archived)
        or (query.actor_id is not None and record.actor_id != query.actor_id)
        or (query.space_id is not None and record.space_id != query.space_id)
        or (query.kind is not None and record.kind != query.kind)
    )


def _item_from_vector_result(
    policy: MemoryRetrievalPolicy,
    item: MemorySearchResult,
    embedding: EmbeddingResult,
) -> RetrievedContextItem:
    return RetrievedContextItem(
        source_id=str(item.record.id),
        source_kind=RetrievalSourceKind.DURABLE_MEMORY,
        prompt_section_kind=policy.prompt_section_kind,
        text=item.record.text,
        score=item.score,
        reason="embedding similarity",
        model_metadata=(embedding.model_metadata,),
        metadata=item.record.metadata,
    )


def _prompt_section(
    policy: MemoryRetrievalPolicy,
    selected: tuple[RetrievedContextItem, ...],
) -> PromptSectionInput | None:
    if not selected:
        return None
    return PromptSectionInput(
        kind=policy.prompt_section_kind,
        title=policy.prompt_title,
        trust_boundary=PromptTrustBoundary.EXTERNAL_CONTEXT,
        items=tuple(item.text for item in selected),
    )


def _reranked_count(result: RerankResult | None) -> int:
    return 0 if result is None else len(result.items)


def _empty_result(
    reason: RetrievalFallbackReason | None,
    *,
    retrieved_count: int = 0,
    embedding_latency_ms: float = 0.0,
    reranking_latency_ms: float = 0.0,
    embedding_cache_hit: bool = False,
) -> RetrievalPipelineResult:
    return RetrievalPipelineResult(
        items=(),
        prompt_section=None,
        observability=RetrievalObservability(
            retrieved_count=retrieved_count,
            reranked_count=0,
            selected_count=0,
            embedding_latency_ms=embedding_latency_ms,
            reranking_latency_ms=reranking_latency_ms,
            embedding_cache_hit=embedding_cache_hit,
            fallback_reason=reason,
        ),
    )


def _elapsed_ms(started: float) -> float:
    return max((time.monotonic() - started) * 1000.0, 0.0)
