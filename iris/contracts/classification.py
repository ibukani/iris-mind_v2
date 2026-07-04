"""小型テキスト分類器の provider-neutral 契約。"""

from __future__ import annotations

from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from iris.contracts.metadata import ImmutableMetadata
from iris.contracts.model_invocation import ModelInvocationMetadata
from iris.core.metadata import immutable_metadata

ClassificationLabel = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ReasonText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ClassificationRequest(BaseModel):
    """分類器へ渡すテキストと候補ラベルの境界モデル。"""

    model_config = ConfigDict(frozen=True)

    text: str
    candidate_labels: tuple[ClassificationLabel, ...] = ()
    model_slot: str | None = None
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


class ClassificationResult(BaseModel):
    """分類器の typed result contract。"""

    model_config = ConfigDict(frozen=True)

    label: ClassificationLabel
    confidence: float = Field(ge=0.0, le=1.0)
    reason: ReasonText
    model_metadata: ModelInvocationMetadata
    latency_ms: float = Field(default=0.0, ge=0.0)
    fallback_applied: bool = False
    original_label: ClassificationLabel | None = None
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


class ClassificationFallbackPolicy(BaseModel):
    """低信頼分類結果を unknown に正規化する deterministic policy。"""

    model_config = ConfigDict(frozen=True)

    confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    unknown_label: ClassificationLabel = "unknown"
    fallback_reason: ReasonText = "classification confidence below threshold"


class TextClassifier(Protocol):
    """小型テキスト分類器 adapter が満たす provider-neutral port。"""

    def classify(self, request: ClassificationRequest) -> ClassificationResult:
        """テキストを分類し、label/confidence/reason/metadata/latency を返す。"""
        ...


def apply_classification_fallback(
    result: ClassificationResult,
    policy: ClassificationFallbackPolicy,
) -> ClassificationResult:
    """低信頼の分類結果を unknown label に正規化する。

    Returns:
        confidence が閾値以上なら元の result、低信頼なら unknown fallback result。
    """
    if result.confidence >= policy.confidence_threshold or result.label == policy.unknown_label:
        return result
    return ClassificationResult(
        label=policy.unknown_label,
        confidence=result.confidence,
        reason=policy.fallback_reason,
        model_metadata=result.model_metadata,
        latency_ms=result.latency_ms,
        fallback_applied=True,
        original_label=result.label,
        metadata=result.metadata,
    )


def classification_result_with_latency(
    result: ClassificationResult,
    *,
    latency_ms: float,
) -> ClassificationResult:
    """既存の分類結果へ観測済み latency を付与したコピーを返す。

    Returns:
        ClassificationResult: latency を差し替えたコピー。
    """
    return ClassificationResult(
        label=result.label,
        confidence=result.confidence,
        reason=result.reason,
        model_metadata=result.model_metadata,
        latency_ms=latency_ms,
        fallback_applied=result.fallback_applied,
        original_label=result.original_label,
        metadata=result.metadata,
    )
