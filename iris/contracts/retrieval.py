"""検索候補 reranker と retrieval pipeline の provider-neutral 契約。"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from iris.contracts.metadata import ImmutableMetadata
from iris.contracts.model_invocation import ModelInvocationMetadata
from iris.core.metadata import immutable_metadata

CandidateId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
RerankReason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
RetrievalReason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class RetrievalSourceKind(StrEnum):
    """Retrieval pipeline が扱う検索対象の種別。"""

    MEMORY = "memory"
    PROJECT_CONTEXT = "project_context"
    TRANSCRIPT = "transcript"


class RetrievalFallbackReason(StrEnum):
    """Retrieval pipeline の deterministic fallback 理由。"""

    NONE = "none"
    NO_RESULTS = "no_results"
    LOW_SCORE = "low_score"
    VECTOR_INDEX_UNAVAILABLE = "vector_index_unavailable"


class RetrievalCandidate(BaseModel):
    """Retrieval pipeline 内で source を横断して扱う検索候補。"""

    model_config = ConfigDict(frozen=True)

    source_id: CandidateId
    source_kind: RetrievalSourceKind
    text: str
    base_score: float = 0.0
    reason: RetrievalReason
    model_metadata: ModelInvocationMetadata | None = None
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


class RetrievalSelectedItem(BaseModel):
    """Prompt context に渡せるまで絞り込まれた retrieval item。"""

    model_config = ConfigDict(frozen=True)

    source_id: CandidateId
    source_kind: RetrievalSourceKind
    text: str
    score: float
    rank: int = Field(ge=1)
    reason: RetrievalReason
    model_metadata: ModelInvocationMetadata
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


class RetrievalPipelineRequest(BaseModel):
    """Embedding search と reranking を行う retrieval pipeline 要求。"""

    model_config = ConfigDict(frozen=True)

    query: str
    source_kinds: tuple[RetrievalSourceKind, ...] = (RetrievalSourceKind.MEMORY,)
    candidate_limit: int = Field(default=20, ge=0)
    limit: int = Field(default=5, ge=0)
    min_score: float = 0.0
    model_slot: str | None = None
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


class RetrievalPipelineResult(BaseModel):
    """Retrieval pipeline の選択結果と監査用メタデータ。"""

    model_config = ConfigDict(frozen=True)

    items: tuple[RetrievalSelectedItem, ...]
    fallback_reason: RetrievalFallbackReason = RetrievalFallbackReason.NONE
    candidate_count: int = Field(ge=0)
    selected_count: int = Field(ge=0)
    dropped_duplicate_count: int = Field(default=0, ge=0)
    cache_hit_count: int = Field(default=0, ge=0)
    cache_miss_count: int = Field(default=0, ge=0)
    embedding_latency_ms: float = Field(default=0.0, ge=0.0)
    reranking_latency_ms: float = Field(default=0.0, ge=0.0)
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


class RetrievalPipelineObservation(BaseModel):
    """Raw text を含めない retrieval observability event。"""

    model_config = ConfigDict(frozen=True)

    event: str = "memory_retrieval.pipeline"
    source_kind: RetrievalSourceKind = RetrievalSourceKind.MEMORY
    candidate_count: int = Field(ge=0)
    selected_count: int = Field(ge=0)
    dropped_duplicate_count: int = Field(default=0, ge=0)
    cache_hit_count: int = Field(default=0, ge=0)
    cache_miss_count: int = Field(default=0, ge=0)
    embedding_latency_ms: float = Field(default=0.0, ge=0.0)
    reranking_latency_ms: float = Field(default=0.0, ge=0.0)
    fallback_reason: RetrievalFallbackReason = RetrievalFallbackReason.NONE
    min_score: float | None = None
    max_score: float | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    reranker_provider: str | None = None
    reranker_model: str | None = None


class RetrievalPipelineObserver(Protocol):
    """Sanitized retrieval pipeline observation を受け取る observer。"""

    def record_retrieval(self, observation: RetrievalPipelineObservation) -> None:
        """Retrieval pipeline の text-free observation を記録する。"""
        ...


class RetrievalSource(Protocol):
    """Memory / project context / transcript を横断する retrieval source port。"""

    @property
    def source_kind(self) -> RetrievalSourceKind:
        """この source が返す候補種別。"""
        ...

    def candidates(self, request: RetrievalPipelineRequest) -> tuple[RetrievalCandidate, ...]:
        """Prompt に直接入れる前の bounded candidate を返す。"""
        ...


class RerankCandidate(BaseModel):
    """Reranker に渡す provider-neutral 検索候補。"""

    model_config = ConfigDict(frozen=True)

    candidate_id: CandidateId
    text: str
    base_score: float = 0.0
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


class RerankRequest(BaseModel):
    """Reranker 呼び出し要求。"""

    model_config = ConfigDict(frozen=True)

    query: str
    candidates: tuple[RerankCandidate, ...]
    limit: int | None = Field(default=None, ge=0)
    model_slot: str | None = None
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


class RerankedItem(BaseModel):
    """Rerank 後の単一候補。"""

    model_config = ConfigDict(frozen=True)

    candidate: RerankCandidate
    score: float
    rank: int = Field(ge=1)
    reason: RerankReason
    model_metadata: ModelInvocationMetadata
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


class RerankResult(BaseModel):
    """Reranker の typed result contract。"""

    model_config = ConfigDict(frozen=True)

    items: tuple[RerankedItem, ...]
    reason: RerankReason
    model_metadata: ModelInvocationMetadata
    latency_ms: float = Field(default=0.0, ge=0.0)
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


class Reranker(Protocol):
    """検索候補を provider-neutral に再順位付けする port。"""

    def rerank(self, request: RerankRequest) -> RerankResult:
        """候補を再順位付けし、score/rank/metadata/latency を返す。"""
        ...


def rerank_result_with_latency(result: RerankResult, *, latency_ms: float) -> RerankResult:
    """既存の rerank result へ観測済み latency を付与したコピーを返す。

    Returns:
        RerankResult: latency を差し替えたコピー。
    """
    return RerankResult(
        items=result.items,
        reason=result.reason,
        model_metadata=result.model_metadata,
        latency_ms=latency_ms,
        metadata=result.metadata,
    )
