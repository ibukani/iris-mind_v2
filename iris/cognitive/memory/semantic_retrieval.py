"""EmbeddingClient / Reranker を使う memory retrieval pipeline。"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import TYPE_CHECKING, override

from iris.cognitive.memory.retrieval import MemoryRetriever
from iris.contracts.embeddings import EmbeddingBatchRequest, EmbeddingRequest
from iris.contracts.memory import (
    MemoryId,
    MemoryQuery,
    MemorySearchResult,
    VectorMemoryIndexError,
    VectorMemorySearchFilter,
)
from iris.contracts.retrieval import (
    RerankCandidate,
    RerankedItem,
    Reranker,
    RerankRequest,
    RetrievalCandidate,
    RetrievalFallbackReason,
    RetrievalPipelineObservation,
    RetrievalPipelineRequest,
    RetrievalPipelineResult,
    RetrievalSelectedItem,
    RetrievalSourceKind,
)
from iris.core.metadata import immutable_metadata

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.contracts.embeddings import EmbeddingClient
    from iris.contracts.memory import (
        MemoryRecord,
        MemoryStore,
        VectorMemoryEntry,
        VectorMemoryIndex,
    )
    from iris.contracts.model_invocation import ModelInvocationMetadata
    from iris.contracts.retrieval import RetrievalPipelineObserver

_MEMORY_RETRIEVAL_MODEL_SLOT = "memory_retrieval"
_VECTOR_REASON = "embedding_similarity"
_LEXICAL_REASON = "lexical_fallback"


@dataclass(frozen=True)
class _CandidateBundle:
    """Memory record と retrieval candidate の対応。"""

    record: MemoryRecord
    candidate: RetrievalCandidate
    vector: tuple[float, ...] | None = None


@dataclass(frozen=True)
class _CandidateSelection:
    """重複除去後候補と除去数。"""

    bundles: tuple[_CandidateBundle, ...]
    dropped_count: int
    latency_ms: float


@dataclass(frozen=True)
class _MissingCandidateEmbeddings:
    """Index に未登録の候補だけに対する一時 embedding 結果。"""

    vectors: dict[str, tuple[float, ...]]
    latency_ms: float


@dataclass(frozen=True)
class SemanticMemoryRetrievalOptions:
    """SemanticMemoryRetriever の検索上限と fallback policy。"""

    fts_limit: int = 10
    vector_limit: int = 20
    candidate_limit: int = 20
    reranker_limit: int = 5
    min_score: float = 0.0
    duplicate_similarity_threshold: float = 0.98


@dataclass(frozen=True)
class SemanticMemoryRetrievalDependencies:
    """SemanticMemoryRetriever が使う store と小型モデル port 群。"""

    store: MemoryStore
    vector_index: VectorMemoryIndex
    embedding: EmbeddingClient
    reranker: Reranker
    fts_retriever: MemoryRetriever | None = None


@dataclass(frozen=True)
class _ResultPayload:
    """RetrievalPipelineResult 構築用の内部値。"""

    items: tuple[RetrievalSelectedItem, ...]
    fallback_reason: RetrievalFallbackReason
    candidate_count: int
    selected_count: int
    dropped_duplicate_count: int
    cache_hit_count: int
    cache_miss_count: int
    embedding_latency_ms: float
    reranking_latency_ms: float
    rerank_reason: str | None = None
    embedding_metadata: ModelInvocationMetadata | None = None
    reranker_metadata: ModelInvocationMetadata | None = None


@dataclass(frozen=True)
class _RerankContext:
    """Rerank selection の観測値と cache 集計。"""

    embedding_metadata: ModelInvocationMetadata
    embedding_latency_ms: float
    vector_unavailable: bool
    cache_hit_count: int
    cache_miss_count: int


class SemanticMemoryRetriever(MemoryRetriever):
    """Embedding search、dedupe、reranking で memory を絞る retriever。"""

    def __init__(
        self,
        dependencies: SemanticMemoryRetrievalDependencies,
        *,
        options: SemanticMemoryRetrievalOptions | None = None,
        observer: RetrievalPipelineObserver | None = None,
    ) -> None:
        """正本 store、派生 index、小型モデル port を注入する。"""
        self._store = dependencies.store
        self._vector_index = dependencies.vector_index
        self._embedding = dependencies.embedding
        self._reranker = dependencies.reranker
        self._fts_retriever = dependencies.fts_retriever
        self._options = options or SemanticMemoryRetrievalOptions()
        self._observer = observer

    @override
    def search(self, query: MemoryQuery) -> Sequence[MemorySearchResult]:
        """MemoryRetriever 互換の検索結果を返す。

        Returns:
            Sequence[MemorySearchResult]: Reranking 後の memory results。
        """
        detailed = self.search_with_details(query)
        records = self._records_by_source_id(detailed.items, query)
        return tuple(
            MemorySearchResult(record=record, score=item.score)
            for item in detailed.items
            if (record := records.get(item.source_id)) is not None
        )

    def search_with_details(self, query: MemoryQuery) -> RetrievalPipelineResult:
        """#94 用の source/score/reason/model metadata 付き検索を行う。

        Returns:
            RetrievalPipelineResult: source ID、score、reason、model metadata 付き結果。
        """
        if query.limit <= 0:
            result = self._empty_result(RetrievalFallbackReason.NO_RESULTS)
            self._record_observation(result, None, None)
            return result

        request = self._request_for_query(query)
        if request.limit <= 0:
            result = self._empty_result(RetrievalFallbackReason.NO_RESULTS)
            self._record_observation(result, None, None)
            return result

        embedding_result = self._embedding.embed_text(
            EmbeddingRequest(
                text=query.text,
                model_slot=request.model_slot,
                metadata=request.metadata,
            )
        )
        vector_bundles, vector_unavailable = self._vector_candidates(query, embedding_result.vector)
        lexical_bundles = self._lexical_candidates(query)
        merged_bundles = self._merge_candidates(vector_bundles, lexical_bundles)
        limited_bundles = merged_bundles[: request.candidate_limit]
        cache_miss_count = _cache_miss_count(vector_bundles, lexical_bundles)
        selection = self._drop_overlapping(limited_bundles)
        rerank_context = _RerankContext(
            embedding_metadata=embedding_result.model_metadata,
            embedding_latency_ms=embedding_result.latency_ms + selection.latency_ms,
            vector_unavailable=vector_unavailable,
            cache_hit_count=len(vector_bundles),
            cache_miss_count=cache_miss_count,
        )
        result = self._rerank_and_select(request, selection, rerank_context)
        self._record_observation(
            result,
            embedding_result.model_metadata,
            _reranker_metadata(result),
        )
        return result

    def _request_for_query(self, query: MemoryQuery) -> RetrievalPipelineRequest:
        limit = min(query.limit, self._options.reranker_limit)
        return RetrievalPipelineRequest(
            query=query.text,
            source_kinds=(RetrievalSourceKind.MEMORY,),
            candidate_limit=max(limit, self._options.candidate_limit),
            limit=limit,
            min_score=self._options.min_score,
            model_slot=_MEMORY_RETRIEVAL_MODEL_SLOT,
        )

    def _vector_candidates(
        self,
        query: MemoryQuery,
        query_vector: Sequence[float],
    ) -> tuple[tuple[_CandidateBundle, ...], bool]:
        try:
            raw_results = self._vector_index.search(
                query_vector,
                limit=self._options.vector_limit,
                filters=VectorMemorySearchFilter(
                    actor_id=query.actor_id,
                    space_id=query.space_id,
                    kind=query.kind,
                    include_archived=query.include_archived,
                ),
            )
        except VectorMemoryIndexError:
            return (), True
        bundles = tuple(
            bundle
            for result in raw_results
            if (
                bundle := self._bundle_from_memory_id(
                    result.memory_id,
                    result.score,
                    _VECTOR_REASON,
                )
            )
            is not None
            and _matches_query(bundle.record, query)
        )
        return bundles, False

    def _bundle_from_memory_id(
        self,
        memory_id: MemoryId,
        score: float,
        reason: str,
    ) -> _CandidateBundle | None:
        record = self._store.get(memory_id)
        if record is None:
            return None
        entry = self._index_entry(record.id)
        return _CandidateBundle(
            record=record,
            candidate=RetrievalCandidate(
                source_id=str(record.id),
                source_kind=RetrievalSourceKind.MEMORY,
                text=record.text,
                base_score=score,
                reason=reason,
                metadata=record.metadata,
            ),
            vector=entry.vector if entry is not None else None,
        )

    def _lexical_candidates(self, query: MemoryQuery) -> tuple[_CandidateBundle, ...]:
        if self._fts_retriever is None or self._options.fts_limit <= 0:
            return ()
        fts_query = MemoryQuery(
            text=query.text,
            actor_id=query.actor_id,
            space_id=query.space_id,
            limit=self._options.fts_limit,
            kind=query.kind,
            include_archived=query.include_archived,
        )
        return tuple(
            _CandidateBundle(
                record=result.record,
                candidate=RetrievalCandidate(
                    source_id=str(result.record.id),
                    source_kind=RetrievalSourceKind.MEMORY,
                    text=result.record.text,
                    base_score=result.score,
                    reason=_LEXICAL_REASON,
                    metadata=result.record.metadata,
                ),
                vector=(
                    entry.vector
                    if (entry := self._index_entry(result.record.id)) is not None
                    else None
                ),
            )
            for result in self._fts_retriever.search(fts_query)
        )

    @staticmethod
    def _merge_candidates(
        first: Sequence[_CandidateBundle],
        second: Sequence[_CandidateBundle],
    ) -> tuple[_CandidateBundle, ...]:
        merged: dict[str, _CandidateBundle] = {}
        for bundle in (*first, *second):
            existing = merged.get(bundle.candidate.source_id)
            if existing is None or bundle.candidate.base_score > existing.candidate.base_score:
                merged[bundle.candidate.source_id] = bundle
        return tuple(merged.values())

    def _drop_overlapping(self, bundles: tuple[_CandidateBundle, ...]) -> _CandidateSelection:
        if len(bundles) <= 1:
            return _CandidateSelection(bundles=bundles, dropped_count=0, latency_ms=0.0)
        text_digests: set[str] = set()
        kept: list[_CandidateBundle] = []
        dropped = 0
        missing_vector_embeddings = self._embed_missing_candidate_vectors(bundles)
        kept_vectors: list[tuple[float, ...]] = []
        for bundle in bundles:
            digest = _normalized_text_digest(bundle.record.text)
            if digest in text_digests:
                dropped += 1
                continue
            vector = bundle.vector or missing_vector_embeddings.vectors.get(
                bundle.candidate.source_id
            )
            if vector is not None and _has_overlapping_vector(
                vector,
                kept_vectors,
                threshold=self._options.duplicate_similarity_threshold,
            ):
                dropped += 1
                continue
            text_digests.add(digest)
            if vector is not None:
                kept_vectors.append(vector)
            kept.append(bundle)
        return _CandidateSelection(
            bundles=tuple(kept),
            dropped_count=dropped,
            latency_ms=missing_vector_embeddings.latency_ms,
        )

    def _embed_missing_candidate_vectors(
        self, bundles: tuple[_CandidateBundle, ...]
    ) -> _MissingCandidateEmbeddings:
        missing = tuple(bundle for bundle in bundles if bundle.vector is None)
        if not missing:
            return _MissingCandidateEmbeddings(vectors={}, latency_ms=0.0)
        batch_result = self._embedding.embed_text_batch(
            EmbeddingBatchRequest(
                texts=tuple(bundle.record.text for bundle in missing),
                model_slot=_MEMORY_RETRIEVAL_MODEL_SLOT,
            )
        )
        vectors = {
            bundle.candidate.source_id: embedding_result.vector
            for bundle, embedding_result in zip(missing, batch_result.embeddings, strict=True)
        }
        return _MissingCandidateEmbeddings(vectors=vectors, latency_ms=batch_result.latency_ms)

    def _index_entry(self, memory_id: MemoryId) -> VectorMemoryEntry | None:
        try:
            return self._vector_index.entry(memory_id)
        except VectorMemoryIndexError:
            return None

    def _rerank_and_select(
        self,
        request: RetrievalPipelineRequest,
        selection: _CandidateSelection,
        context: _RerankContext,
    ) -> RetrievalPipelineResult:
        if not selection.bundles:
            fallback = (
                RetrievalFallbackReason.VECTOR_INDEX_UNAVAILABLE
                if context.vector_unavailable
                else RetrievalFallbackReason.NO_RESULTS
            )
            return self._result(
                _ResultPayload(
                    items=(),
                    fallback_reason=fallback,
                    candidate_count=0,
                    selected_count=0,
                    dropped_duplicate_count=selection.dropped_count,
                    cache_hit_count=context.cache_hit_count,
                    cache_miss_count=context.cache_miss_count,
                    embedding_latency_ms=context.embedding_latency_ms,
                    reranking_latency_ms=0.0,
                )
            )
        rerank_result = self._reranker.rerank(
            RerankRequest(
                query=request.query,
                candidates=tuple(_to_rerank_candidate(bundle) for bundle in selection.bundles),
                limit=request.limit,
                model_slot=request.model_slot,
                metadata=request.metadata,
            )
        )
        records = {bundle.candidate.source_id: bundle.record for bundle in selection.bundles}
        selected_items = tuple(
            item
            for reranked in rerank_result.items
            if reranked.score >= request.min_score
            and (record := records.get(reranked.candidate.candidate_id)) is not None
            for item in (_selected_item(reranked, record),)
        )
        fallback = _fallback_for_selected(
            selected_count=len(selected_items),
            had_candidates=bool(selection.bundles),
            vector_unavailable=context.vector_unavailable,
        )
        return self._result(
            _ResultPayload(
                items=selected_items,
                fallback_reason=fallback,
                candidate_count=len(selection.bundles),
                selected_count=len(selected_items),
                dropped_duplicate_count=selection.dropped_count,
                cache_hit_count=context.cache_hit_count,
                cache_miss_count=context.cache_miss_count,
                embedding_latency_ms=context.embedding_latency_ms,
                reranking_latency_ms=rerank_result.latency_ms,
                rerank_reason=rerank_result.reason,
                embedding_metadata=context.embedding_metadata,
                reranker_metadata=rerank_result.model_metadata,
            )
        )

    @staticmethod
    def _result(payload: _ResultPayload) -> RetrievalPipelineResult:
        metadata_values: dict[str, str] = {}
        if payload.rerank_reason is not None:
            metadata_values["rerank_reason"] = payload.rerank_reason
        if payload.embedding_metadata is not None:
            metadata_values["embedding_provider"] = payload.embedding_metadata.provider
            metadata_values["embedding_model"] = payload.embedding_metadata.model_name
        if payload.reranker_metadata is not None:
            metadata_values["reranker_provider"] = payload.reranker_metadata.provider
            metadata_values["reranker_model"] = payload.reranker_metadata.model_name
        return RetrievalPipelineResult(
            items=payload.items,
            fallback_reason=payload.fallback_reason,
            candidate_count=payload.candidate_count,
            selected_count=payload.selected_count,
            dropped_duplicate_count=payload.dropped_duplicate_count,
            cache_hit_count=payload.cache_hit_count,
            cache_miss_count=payload.cache_miss_count,
            embedding_latency_ms=payload.embedding_latency_ms,
            reranking_latency_ms=payload.reranking_latency_ms,
            metadata=immutable_metadata(metadata_values),
        )

    @staticmethod
    def _empty_result(fallback_reason: RetrievalFallbackReason) -> RetrievalPipelineResult:
        return RetrievalPipelineResult(
            items=(),
            fallback_reason=fallback_reason,
            candidate_count=0,
            selected_count=0,
        )

    def _records_by_source_id(
        self,
        items: Sequence[RetrievalSelectedItem],
        query: MemoryQuery,
    ) -> dict[str, MemoryRecord]:
        records: dict[str, MemoryRecord] = {}
        for item in items:
            record = self._store.get(MemoryId(item.source_id))
            if record is not None and _matches_query(record, query):
                records[item.source_id] = record
        return records

    def _record_observation(
        self,
        result: RetrievalPipelineResult,
        embedding_metadata: ModelInvocationMetadata | None,
        reranker_metadata: ModelInvocationMetadata | None,
    ) -> None:
        if self._observer is None:
            return
        scores = tuple(item.score for item in result.items)
        self._observer.record_retrieval(
            RetrievalPipelineObservation(
                candidate_count=result.candidate_count,
                selected_count=result.selected_count,
                dropped_duplicate_count=result.dropped_duplicate_count,
                cache_hit_count=result.cache_hit_count,
                cache_miss_count=result.cache_miss_count,
                embedding_latency_ms=result.embedding_latency_ms,
                reranking_latency_ms=result.reranking_latency_ms,
                fallback_reason=result.fallback_reason,
                min_score=min(scores) if scores else None,
                max_score=max(scores) if scores else None,
                embedding_provider=embedding_metadata.provider if embedding_metadata else None,
                embedding_model=embedding_metadata.model_name if embedding_metadata else None,
                reranker_provider=reranker_metadata.provider if reranker_metadata else None,
                reranker_model=reranker_metadata.model_name if reranker_metadata else None,
            )
        )


def _cache_miss_count(
    vector_bundles: Sequence[_CandidateBundle],
    lexical_bundles: Sequence[_CandidateBundle],
) -> int:
    vector_source_ids = {bundle.candidate.source_id for bundle in vector_bundles}
    return sum(
        1 for bundle in lexical_bundles if bundle.candidate.source_id not in vector_source_ids
    )


def _matches_query(record: MemoryRecord, query: MemoryQuery) -> bool:
    return (
        (query.include_archived or not record.archived)
        and (query.actor_id is None or record.actor_id == query.actor_id)
        and (query.space_id is None or record.space_id == query.space_id)
        and (query.kind is None or record.kind == query.kind)
    )


def _to_rerank_candidate(bundle: _CandidateBundle) -> RerankCandidate:
    return RerankCandidate(
        candidate_id=bundle.candidate.source_id,
        text=bundle.candidate.text,
        base_score=bundle.candidate.base_score,
        metadata=bundle.candidate.metadata,
    )


def _selected_item(reranked: RerankedItem, record: MemoryRecord) -> RetrievalSelectedItem:
    return RetrievalSelectedItem(
        source_id=str(record.id),
        source_kind=RetrievalSourceKind.MEMORY,
        text=record.text,
        score=reranked.score,
        rank=reranked.rank,
        reason=reranked.reason,
        model_metadata=reranked.model_metadata,
        metadata=record.metadata,
    )


def _fallback_for_selected(
    *,
    selected_count: int,
    had_candidates: bool,
    vector_unavailable: bool,
) -> RetrievalFallbackReason:
    if vector_unavailable:
        return RetrievalFallbackReason.VECTOR_INDEX_UNAVAILABLE
    if selected_count > 0:
        return RetrievalFallbackReason.NONE
    if had_candidates:
        return RetrievalFallbackReason.LOW_SCORE
    return RetrievalFallbackReason.NO_RESULTS


def _normalized_text_digest(text: str) -> str:
    normalized = " ".join(text.casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _has_overlapping_vector(
    vector: Sequence[float],
    kept_vectors: Sequence[Sequence[float]],
    *,
    threshold: float,
) -> bool:
    return any(_cosine_similarity(vector, kept) >= threshold for kept in kept_vectors)


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _reranker_metadata(result: RetrievalPipelineResult) -> ModelInvocationMetadata | None:
    if not result.items:
        return None
    return result.items[0].model_metadata
