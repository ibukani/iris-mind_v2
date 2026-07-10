"""TextClassifier adapter 間で共有する結果生成。"""

from __future__ import annotations

from dataclasses import dataclass

from iris.contracts.classification import (
    ClassificationFallbackPolicy,
    ClassificationResult,
)
from iris.contracts.model_invocation import ModelInvocationMetadata
from iris.contracts.model_policy import ModelCallKind


@dataclass(frozen=True)
class ClassificationResultFactory:
    """Adapter 固有 metadata と unknown 結果の生成を束ねる。"""

    fallback_policy: ClassificationFallbackPolicy
    provider: str
    model_name: str
    adapter_name: str

    def metadata_for_slot(self, model_slot: str | None) -> ModelInvocationMetadata:
        """分類呼び出し metadata を返す。

        Returns:
            Adapter 固有情報を持つ model invocation metadata。
        """
        return ModelInvocationMetadata(
            call_kind=ModelCallKind.SMALL_CLASSIFIER,
            provider=self.provider,
            model_name=self.model_name,
            adapter_name=self.adapter_name,
            model_slot=model_slot,
        )

    def unknown(self, model_slot: str | None, *, reason: str) -> ClassificationResult:
        """Confidence 0 の unknown 結果を返す。

        Returns:
            Adapter metadata を保持した unknown classification result。
        """
        return ClassificationResult(
            label=self.fallback_policy.unknown_label,
            confidence=0.0,
            reason=reason,
            model_metadata=self.metadata_for_slot(model_slot),
            latency_ms=0.0,
        )


def label_allowed(label: str, candidate_labels: tuple[str, ...]) -> bool:
    """候補 label 制約に対して label が許可されるか返す。

    Returns:
        候補未指定または候補内なら True。
    """
    return not candidate_labels or label in candidate_labels
