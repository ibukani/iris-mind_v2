"""検索候補 reranker と retrieval pipeline の provider-neutral 契約。"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from iris.contracts.metadata import ImmutableMetadata
from iris.contracts.model_invocation import ModelInvocationMetadata
from iris.contracts.prompting import PromptSectionInput, PromptSectionKind
from iris.core.metadata import immutable_metadata

CandidateId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
RerankReason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
RetrievalReason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class RetrievalSourceKind(StrEnum):
    """Retrieval item の出所種別。"""

    DURABLE_MEMORY = "durable_memory"
    PROJECT_CONTEXT = "project_context"
    TRANSCRIPT = "transcript"
    REVIEW_CANDIDATE = "review_candidate"


class RetrievalFallbackReason(StrEnum):
    """Retrieval pipeline が fallback した理由。"""

    EMPTY_QUERY = "empty_query"
    EMPTY_INDEX = "empty_index"
    QUERY_LIMIT_ZERO = "query_limit_zero"
    EMBEDDING_UNAVAILABLE = "embedding_unavailable"
    EMBEDDING_TIMEOUT = "embedding_timeout"
    RECORD_REFRESH_UNAVAILABLE = "record_refresh_unavailable"
    VECTOR_INDEX_UNAVAILABLE = "vector_index_unavailable"
    RERANKER_UNAVAILABLE = "reranker_unavailable"
    RERANKER_TIMEOUT = "reranker_timeout"
    PROMPT_BUDGET_ZERO = "prompt_budget_zero"
    LOW_SCORE = "low_score"


class RetrievedContextItem(BaseModel):
    """Prompt context へ渡せる retrieval 済み item。"""

    model_config = ConfigDict(frozen=True)

    source_id: CandidateId
    source_kind: RetrievalSourceKind
    prompt_section_kind: PromptSectionKind
    text: str
    score: float
    reason: RetrievalReason
    model_metadata: tuple[ModelInvocationMetadata, ...] = ()
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


class RetrievalOverlapItem(BaseModel):
    """Embedding similarity で検出した重複・重なり候補。"""

    model_config = ConfigDict(frozen=True)

    left_source_id: CandidateId
    right_source_id: CandidateId
    source_kind: RetrievalSourceKind
    score: float = Field(ge=-1.0, le=1.0)
    reason: RetrievalReason
    model_metadata: ModelInvocationMetadata
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


class RetrievalObservability(BaseModel):
    """Retrieval pipeline の安全な観測 metadata。"""

    model_config = ConfigDict(frozen=True)

    retrieved_count: int = Field(ge=0)
    reranked_count: int = Field(ge=0)
    selected_count: int = Field(ge=0)
    embedding_latency_ms: float = Field(default=0.0, ge=0.0)
    reranking_latency_ms: float = Field(default=0.0, ge=0.0)
    embedding_cache_hit: bool = False
    record_embedding_scanned: int = Field(default=0, ge=0)
    record_embedding_upserted: int = Field(default=0, ge=0)
    record_embedding_unchanged: int = Field(default=0, ge=0)
    record_embedding_missing: int = Field(default=0, ge=0)
    record_embedding_stale: int = Field(default=0, ge=0)
    record_embedding_incompatible: int = Field(default=0, ge=0)
    fallback_reason: RetrievalFallbackReason | None = None


class RetrievalPipelineResult(BaseModel):
    """Retrieval pipeline の選択済み context と prompt section。"""

    model_config = ConfigDict(frozen=True)

    items: tuple[RetrievedContextItem, ...]
    prompt_section: PromptSectionInput | None = None
    observability: RetrievalObservability


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
