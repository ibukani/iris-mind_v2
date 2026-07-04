"""埋め込みモデルのプロバイダ中立契約。"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from iris.contracts.metadata import ImmutableMetadata
from iris.contracts.model_invocation import ModelInvocationMetadata
from iris.core.metadata import immutable_metadata


class EmbeddingModel(Protocol):
    """テキストを固定次元ベクトルへ変換する契約。"""

    @property
    def provider(self) -> str:
        """Index compatibility 判定に使う provider 識別子。"""
        ...

    @property
    def model_id(self) -> str:
        """Index compatibility 判定に使う安定したモデル識別子。"""
        ...

    @property
    def dimension(self) -> int:
        """出力ベクトルの次元数。"""
        ...

    def embed(self, text: str) -> tuple[float, ...]:
        """単一テキストを埋め込む。"""
        ...

    def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        """テキスト群を入力順で埋め込む。"""
        ...


class EmbeddingRequest(BaseModel):
    """EmbeddingClient へ渡す単一テキスト要求。"""

    model_config = ConfigDict(frozen=True)

    text: str
    model_slot: str | None = None
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


class EmbeddingBatchRequest(BaseModel):
    """EmbeddingClient へ渡す batch 要求。"""

    model_config = ConfigDict(frozen=True)

    texts: tuple[str, ...]
    model_slot: str | None = None
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


class EmbeddingResult(BaseModel):
    """単一 embedding の typed result contract。"""

    model_config = ConfigDict(frozen=True)

    vector: tuple[float, ...]
    dimension: int = Field(gt=0)
    reason: str
    model_metadata: ModelInvocationMetadata
    latency_ms: float = Field(default=0.0, ge=0.0)
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


class EmbeddingBatchResult(BaseModel):
    """Batch embedding の typed result contract。"""

    model_config = ConfigDict(frozen=True)

    embeddings: tuple[EmbeddingResult, ...]
    reason: str
    model_metadata: ModelInvocationMetadata
    latency_ms: float = Field(default=0.0, ge=0.0)
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


class EmbeddingClient(Protocol):
    """小型 embedding adapter が満たす provider-neutral port。"""

    @property
    def provider(self) -> str:
        """Provider 識別子を返す。"""
        ...

    @property
    def model_id(self) -> str:
        """モデル識別子を返す。"""
        ...

    @property
    def dimension(self) -> int:
        """Embedding dimension を返す。"""
        ...

    def embed_text(self, request: EmbeddingRequest) -> EmbeddingResult:
        """単一テキストを埋め込み、metadata 付き result を返す。"""
        ...

    def embed_text_batch(self, request: EmbeddingBatchRequest) -> EmbeddingBatchResult:
        """複数テキストを入力順で埋め込み、metadata 付き result を返す。"""
        ...


def embedding_result_with_latency(result: EmbeddingResult, *, latency_ms: float) -> EmbeddingResult:
    """単一 embedding result へ観測済み latency を付与したコピーを返す。

    Returns:
        EmbeddingResult: latency を差し替えたコピー。
    """
    return EmbeddingResult(
        vector=result.vector,
        dimension=result.dimension,
        reason=result.reason,
        model_metadata=result.model_metadata,
        latency_ms=latency_ms,
        metadata=result.metadata,
    )


def embedding_batch_result_with_latency(
    result: EmbeddingBatchResult,
    *,
    latency_ms: float,
) -> EmbeddingBatchResult:
    """Batch embedding result へ観測済み latency を付与したコピーを返す。

    Returns:
        EmbeddingBatchResult: latency を差し替えたコピー。
    """
    return EmbeddingBatchResult(
        embeddings=result.embeddings,
        reason=result.reason,
        model_metadata=result.model_metadata,
        latency_ms=latency_ms,
        metadata=result.metadata,
    )
