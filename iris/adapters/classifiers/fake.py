"""テスト・開発用の決定論的 TextClassifier adapter。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from iris.adapters.classifiers.results import ClassificationResultFactory, label_allowed
from iris.contracts.classification import (
    ClassificationFallbackPolicy,
    ClassificationLabel,
    ClassificationRequest,
    ClassificationResult,
    apply_classification_fallback,
)

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
        self._results = ClassificationResultFactory(
            fallback_policy=fallback_policy or ClassificationFallbackPolicy(),
            provider="fake",
            model_name=model,
            adapter_name="fake_text_classifier",
        )

    def classify(self, request: ClassificationRequest) -> ClassificationResult:
        """完全一致 fixture を返し、未定義入力は unknown にする。

        Returns:
            ClassificationResult: fixture または unknown fallback。
        """
        case = self._cases.get(request.text)
        if case is None:
            result = self._results.unknown(
                request.model_slot,
                reason="no fake classification fixture matched",
            )
        elif not label_allowed(case.label, request.candidate_labels):
            result = self._results.unknown(
                request.model_slot,
                reason="classification label outside candidate labels",
            )
        else:
            result = ClassificationResult(
                label=case.label,
                confidence=case.confidence,
                reason=case.reason,
                model_metadata=self._results.metadata_for_slot(request.model_slot),
                latency_ms=0.0,
            )
        return apply_classification_fallback(result, self._results.fallback_policy)
