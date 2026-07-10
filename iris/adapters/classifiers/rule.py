"""決定論的 rule-based 小型テキスト分類器 adapter。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

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

Keyword = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ClassificationRule(BaseModel):
    """Keyword が含まれる場合に固定 label を返す分類 rule。"""

    model_config = ConfigDict(frozen=True)

    label: ClassificationLabel
    keywords: tuple[Keyword, ...]
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reason: str = "keyword rule matched"


class RuleBasedTextClassifier:
    """Keyword rule を上から評価する決定論的 TextClassifier。"""

    def __init__(
        self,
        rules: Sequence[ClassificationRule],
        *,
        fallback_policy: ClassificationFallbackPolicy | None = None,
        model: str = "rule-v1",
    ) -> None:
        """分類 rule と fallback policy を注入する。"""
        self._rules = tuple(rules)
        self._results = ClassificationResultFactory(
            fallback_policy=fallback_policy or ClassificationFallbackPolicy(),
            provider="rule",
            model_name=model,
            adapter_name="rule_based_text_classifier",
        )

    def classify(self, request: ClassificationRequest) -> ClassificationResult:
        """Keyword rule に基づいて分類する。

        Returns:
            ClassificationResult: rule match または unknown fallback。
        """
        result = self._first_matching_result(request)
        if not label_allowed(result.label, request.candidate_labels):
            result = self._results.unknown(
                request.model_slot,
                reason="classification label outside candidate labels",
            )
        return apply_classification_fallback(result, self._results.fallback_policy)

    def _first_matching_result(self, request: ClassificationRequest) -> ClassificationResult:
        normalized_text = request.text.casefold()
        for rule in self._rules:
            if _matches_rule(normalized_text, rule):
                return ClassificationResult(
                    label=rule.label,
                    confidence=rule.confidence,
                    reason=rule.reason,
                    model_metadata=self._results.metadata_for_slot(request.model_slot),
                    latency_ms=0.0,
                )
        return self._results.unknown(
            request.model_slot,
            reason="no classification rule matched",
        )


def _matches_rule(normalized_text: str, rule: ClassificationRule) -> bool:
    return any(keyword.casefold() in normalized_text for keyword in rule.keywords)
