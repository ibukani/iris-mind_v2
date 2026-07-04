"""検索候補 reranker の provider-neutral 契約。"""

from __future__ import annotations

from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from iris.contracts.metadata import ImmutableMetadata
from iris.contracts.model_invocation import ModelInvocationMetadata
from iris.core.metadata import immutable_metadata

CandidateId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
RerankReason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


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
