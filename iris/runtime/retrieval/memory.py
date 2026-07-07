"""Prompt budget に接続する bounded memory retrieval pipeline。"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from enum import StrEnum
import time
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, ConfigDict

from iris.contracts.embeddings import EmbeddingBatchRequest, EmbeddingRequest, EmbeddingResult
from iris.contracts.memory import (
    MemoryQuery,
    MemoryRecord,
    MemorySearchResult,
    VectorMemoryEntryMetadata,
    VectorMemoryIndexError,
    VectorMemorySearchFilter,
    memory_record_digest,
    vector_memory_entry_from_record,
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


Clock = Callable[[], float]


class MemoryRecordEmbeddingRefreshStats(BaseModel):
    """Memory record embedding refresh の結果。"""

    model_config = ConfigDict(frozen=True)

    scanned: int = 0
    upserted: int = 0
    unchanged: int = 0
    missing: int = 0
    stale: int = 0
    incompatible: int = 0


class MemoryRecordEmbeddingRefresher(Protocol):
    """Retrieval 前に bounded memory records の vector entry を更新する port。"""

    def refresh(
        self,
        records: tuple[MemoryRecord, ...],
    ) -> MemoryRecordEmbeddingRefreshStats:
        """Missing/stale/incompatible record embeddings を同期する。"""
        ...


class _EntryState(StrEnum):
    MISSING = "missing"
    STALE = "stale"
    INCOMPATIBLE = "incompatible"
    UNCHANGED = "unchanged"


class VectorMemoryRecordEmbeddingRefresher:
    """正本 MemoryRecord と派生 vector entry の freshness を同期する。"""

    def __init__(
        self,
        *,
        index: VectorMemoryIndex,
        embedding_client: EmbeddingClient,
        model_slot: str | None = "memory_record_embedding",
    ) -> None:
        """Vector index、embedding client、model slot を注入する。"""
        self._index = index
        self._embedding_client = embedding_client
        self._model_slot = model_slot

    def refresh(
        self,
        records: tuple[MemoryRecord, ...],
    ) -> MemoryRecordEmbeddingRefreshStats:
        """Fresh entry は再 embedding せず、stale entry だけ upsert する。

        Returns:
            refresh 件数の統計。
        """
        classified = tuple((record, self._classify(record)) for record in records)
        refresh_records = tuple(
            record for record, state in classified if state is not _EntryState.UNCHANGED
        )
        upserted = self._refresh_records(refresh_records)
        return MemoryRecordEmbeddingRefreshStats(
            scanned=len(records),
            upserted=upserted,
            unchanged=sum(state is _EntryState.UNCHANGED for _, state in classified),
            missing=sum(state is _EntryState.MISSING for _, state in classified),
            stale=sum(state is _EntryState.STALE for _, state in classified),
            incompatible=sum(state is _EntryState.INCOMPATIBLE for _, state in classified),
        )

    def _classify(self, record: MemoryRecord) -> _EntryState:
        metadata = self._index.metadata(record.id)
        if metadata is None:
            return _EntryState.MISSING
        if self._is_incompatible(metadata):
            return _EntryState.INCOMPATIBLE
        if metadata.source_digest != memory_record_digest(record):
            return _EntryState.STALE
        return _EntryState.UNCHANGED

    def _is_incompatible(self, metadata: VectorMemoryEntryMetadata) -> bool:
        return (
            metadata.embedding_provider != self._embedding_client.provider
            or metadata.embedding_model != self._embedding_client.model_id
            or metadata.embedding_dimension != self._embedding_client.dimension
        )

    def _refresh_records(self, records: tuple[MemoryRecord, ...]) -> int:
        if not records:
            return 0
        batch = self._embedding_client.embed_text_batch(
            EmbeddingBatchRequest(
                texts=tuple(record.text for record in records),
                model_slot=self._model_slot,
                metadata={"stage": "memory_record_embedding_refresh"},
            )
        )
        for record, embedding in zip(records, batch.embeddings, strict=True):
            self._index.upsert(
                vector_memory_entry_from_record(
                    record,
                    vector=embedding.vector,
                    embedding_provider=self._embedding_client.provider,
                    embedding_model=self._embedding_client.model_id,
                    embedding_dimension=self._embedding_client.dimension,
                )
            )
        return len(records)


@dataclass(frozen=True)
class MemoryRetrievalPolicy:
    """Hot path retrieval の上限と fallback policy。"""

    max_retrieved_candidates: int
    max_reranked_candidates: int
    max_prompt_selected_items: int
    embedding_timeout_ms: float = 250.0
    reranker_timeout_ms: float = 250.0
    min_score: float = 0.0
    prompt_section_kind: PromptSectionKind = PromptSectionKind.USER_MEMORY
    prompt_title: str = "Relevant memories"
    model_slot: str | None = "memory_retrieval"

    def __post_init__(self) -> None:
        """Policy の hot path 上限を検証する。

        Raises:
            ValueError: 上限または timeout が負の値の場合。
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
        if self.embedding_timeout_ms < 0:
            msg = "embedding_timeout_ms must be >= 0"
            raise ValueError(msg)
        if self.reranker_timeout_ms < 0:
            msg = "reranker_timeout_ms must be >= 0"
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
        record_refresher: MemoryRecordEmbeddingRefresher | None = None,
    ) -> None:
        """依存 port と retrieval policy を注入する。"""
        self._store = store
        self._vector_index = vector_index
        self._embedding_client = embedding_client
        self._reranker = reranker
        self._policy = policy
        self._record_refresher = record_refresher
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
        refresh = self._refresh_record_embeddings(query, limits)
        if refresh.failed:
            return _empty_result(
                RetrievalFallbackReason.RECORD_REFRESH_UNAVAILABLE,
                record_refresh=refresh.stats,
            )
        embedding = self._embed_query(query.text)
        if embedding.result is None:
            return _empty_result(
                embedding.fallback_reason,
                embedding_latency_ms=embedding.latency_ms,
                embedding_cache_hit=embedding.cache_hit,
                record_refresh=refresh.stats,
            )
        return self._retrieve_with_embedding(query, limits, embedding, embedding.result, refresh)

    def _retrieve_with_embedding(
        self,
        query: MemoryQuery,
        limits: _RetrievalLimits,
        embedding: _EmbeddingOutcome,
        embedding_result: EmbeddingResult,
        refresh: _RefreshOutcome,
    ) -> RetrievalPipelineResult:
        try:
            retrieved = self._retrieve_vector_candidates(query, embedding_result, limits)
        except VectorMemoryIndexError:
            return _empty_result(
                RetrievalFallbackReason.VECTOR_INDEX_UNAVAILABLE,
                embedding_latency_ms=embedding.latency_ms,
                embedding_cache_hit=embedding.cache_hit,
                record_refresh=refresh.stats,
            )
        if not retrieved:
            return _empty_result(
                RetrievalFallbackReason.EMPTY_INDEX,
                embedding_latency_ms=embedding.latency_ms,
                embedding_cache_hit=embedding.cache_hit,
                record_refresh=refresh.stats,
            )

        reranked = self._rerank(query.text, retrieved, limits)
        if reranked.fallback_reason is RetrievalFallbackReason.RERANKER_TIMEOUT:
            return _empty_result(
                RetrievalFallbackReason.RERANKER_TIMEOUT,
                retrieved_count=len(retrieved),
                embedding_latency_ms=embedding.latency_ms,
                reranking_latency_ms=reranked.latency_ms,
                embedding_cache_hit=embedding.cache_hit,
                record_refresh=refresh.stats,
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
                record_embedding_scanned=refresh.stats.scanned,
                record_embedding_upserted=refresh.stats.upserted,
                record_embedding_unchanged=refresh.stats.unchanged,
                record_embedding_missing=refresh.stats.missing,
                record_embedding_stale=refresh.stats.stale,
                record_embedding_incompatible=refresh.stats.incompatible,
                fallback_reason=fallback or reranked.fallback_reason,
            ),
        )

    def _refresh_record_embeddings(
        self,
        query: MemoryQuery,
        limits: _RetrievalLimits,
    ) -> _RefreshOutcome:
        if self._record_refresher is None or limits.max_retrieved_candidates == 0:
            return _RefreshOutcome(stats=MemoryRecordEmbeddingRefreshStats())
        candidates = self._store.search(
            MemoryQuery(
                text=query.text,
                actor_id=query.actor_id,
                space_id=query.space_id,
                limit=limits.max_retrieved_candidates,
                kind=query.kind,
                include_archived=query.include_archived,
            )
        )
        records = tuple(result.record for result in candidates)
        try:
            stats = self._record_refresher.refresh(records)
        except (RuntimeError, ValueError, VectorMemoryIndexError):
            return _RefreshOutcome(
                stats=MemoryRecordEmbeddingRefreshStats(scanned=len(records)),
                failed=True,
            )
        return _RefreshOutcome(stats=stats)

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
            result = _run_with_timeout(
                lambda: self._embedding_client.embed_text(
                    EmbeddingRequest(
                        text=text,
                        model_slot=self._policy.model_slot,
                        metadata={"stage": "memory_retrieval_query"},
                    )
                ),
                timeout_ms=self._policy.embedding_timeout_ms,
            )
            if result.timed_out:
                return _EmbeddingOutcome(
                    result=None,
                    latency_ms=result.latency_ms,
                    cache_hit=False,
                    fallback_reason=RetrievalFallbackReason.EMBEDDING_TIMEOUT,
                )
        except (RuntimeError, ValueError) as exc:
            return _EmbeddingOutcome(
                result=None,
                latency_ms=_elapsed_ms(time.monotonic, started),
                cache_hit=False,
                fallback_reason=RetrievalFallbackReason.EMBEDDING_UNAVAILABLE,
                error_message=str(exc),
            )
        latency_ms = result.latency_ms or _elapsed_ms(time.monotonic, started)
        if result.value is None:
            return _EmbeddingOutcome(
                result=None,
                latency_ms=latency_ms,
                cache_hit=False,
                fallback_reason=RetrievalFallbackReason.EMBEDDING_UNAVAILABLE,
            )
        self._query_embedding_cache[key] = result.value
        return _EmbeddingOutcome(result=result.value, latency_ms=latency_ms, cache_hit=False)

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
            result = _run_with_timeout(
                lambda: reranker.rerank(
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
                ),
                timeout_ms=self._policy.reranker_timeout_ms,
            )
            if result.timed_out:
                return _RerankOutcome(
                    result=None,
                    latency_ms=result.latency_ms,
                    fallback_reason=RetrievalFallbackReason.RERANKER_TIMEOUT,
                )
        except (RuntimeError, ValueError) as exc:
            return _RerankOutcome(
                result=None,
                latency_ms=_elapsed_ms(time.monotonic, started),
                fallback_reason=RetrievalFallbackReason.RERANKER_UNAVAILABLE,
                error_message=str(exc),
            )
        latency_ms = result.latency_ms or _elapsed_ms(time.monotonic, started)
        return _RerankOutcome(result=result.value, latency_ms=latency_ms)

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
class _RefreshOutcome:
    stats: MemoryRecordEmbeddingRefreshStats
    failed: bool = False


@dataclass(frozen=True)
class _RetrievalLimits:
    max_retrieved_candidates: int
    max_reranked_candidates: int
    max_prompt_selected_items: int


@dataclass(frozen=True)
class _TimedCallResult[T]:
    value: T | None
    latency_ms: float
    timed_out: bool = False


def _run_with_timeout[T](
    call: Callable[[], T],
    *,
    timeout_ms: float,
) -> _TimedCallResult[T]:
    started = time.monotonic()
    timeout_seconds = timeout_ms / 1000.0
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="iris-retrieval")
    future = executor.submit(call)
    timed_out = False
    try:
        value = future.result(timeout=timeout_seconds)
    except FutureTimeoutError:
        timed_out = True
        future.cancel()
        return _TimedCallResult(
            value=None,
            latency_ms=_elapsed_ms(time.monotonic, started),
            timed_out=True,
        )
    finally:
        executor.shutdown(wait=not timed_out, cancel_futures=True)
    return _TimedCallResult(value=value, latency_ms=_elapsed_ms(time.monotonic, started))


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
    record_refresh: MemoryRecordEmbeddingRefreshStats | None = None,
) -> RetrievalPipelineResult:
    refresh = record_refresh or MemoryRecordEmbeddingRefreshStats()
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
            record_embedding_scanned=refresh.scanned,
            record_embedding_upserted=refresh.upserted,
            record_embedding_unchanged=refresh.unchanged,
            record_embedding_missing=refresh.missing,
            record_embedding_stale=refresh.stale,
            record_embedding_incompatible=refresh.incompatible,
            fallback_reason=reason,
        ),
    )


def _elapsed_ms(clock: Clock, started: float) -> float:
    return max((clock() - started) * 1000.0, 0.0)
