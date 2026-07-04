"""テスト・開発用の決定論的 TextClassifier adapter。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from iris.contracts.classification import (
    ClassificationFallbackPolicy,
    ClassificationLabel,
    ClassificationRequest,
    ClassificationResult,
    apply_classification_fallback,
)
from iris.contracts.model_invocation import ModelInvocationMetadata
from iris.contracts.model_policy import ModelCallKind

if TYPE_CHECKING:
    from collections.abc import Sequence


class FakeClassificationCase(BaseModel):
    """FakeTextClassifier が入力 text に対して返す固定分類。"""

    model_config = ConfigDict(frozen=True)

    text: str
    label: ClassificationLabel
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = "fake classification fixture"


class FakeTextClassifier:
    """入力 text ごとの fixture 結果を返す TextClassifier。"""

    def __init__(
        self,
        cases: Sequence[FakeClassificationCase] = (),
        *,
        fallback_policy: ClassificationFallbackPolicy | None = None,
        model: str = "fake-classifier-v1",
    ) -> None:
        """固定分類 fixture と fallback policy を注入する。"""
        self._cases = {case.text: case for case in cases}
        self._fallback_policy = fallback_policy or ClassificationFallbackPolicy()
        self._model = model

    def classify(self, request: ClassificationRequest) -> ClassificationResult:
        """完全一致 fixture を返し、未定義入力は unknown にする。

        Returns:
            ClassificationResult: fixture または unknown fallback。
        """
        case = self._cases.get(request.text)
        if case is None:
            result = self._unknown_result(request, reason="no fake classification fixture matched")
        elif not _label_allowed(case.label, request.candidate_labels):
            result = self._unknown_result(
                request,
                reason="classification label outside candidate labels",
            )
        else:
            result = ClassificationResult(
                label=case.label,
                confidence=case.confidence,
                reason=case.reason,
                model_metadata=self._metadata_for_slot(request.model_slot),
                latency_ms=0.0,
            )
        return apply_classification_fallback(result, self._fallback_policy)

    def _unknown_result(
        self, request: ClassificationRequest, *, reason: str
    ) -> ClassificationResult:
        return ClassificationResult(
            label=self._fallback_policy.unknown_label,
            confidence=0.0,
            reason=reason,
            model_metadata=self._metadata_for_slot(request.model_slot),
            latency_ms=0.0,
        )

    def _metadata_for_slot(self, model_slot: str | None) -> ModelInvocationMetadata:
        return ModelInvocationMetadata(
            call_kind=ModelCallKind.SMALL_CLASSIFIER,
            provider="fake",
            model_name=self._model,
            adapter_name="fake_text_classifier",
            model_slot=model_slot,
        )


def _label_allowed(label: str, candidate_labels: tuple[str, ...]) -> bool:
    return not candidate_labels or label in candidate_labels
