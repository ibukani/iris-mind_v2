"""決定論的 rule-based 小型テキスト分類器 adapter。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

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
        self._fallback_policy = fallback_policy or ClassificationFallbackPolicy()
        self._model = model

    def classify(self, request: ClassificationRequest) -> ClassificationResult:
        """Keyword rule に基づいて分類する。

        Returns:
            ClassificationResult: rule match または unknown fallback。
        """
        result = self._first_matching_result(request)
        if not _label_allowed(result.label, request.candidate_labels):
            result = self._unknown_result(
                request,
                reason="classification label outside candidate labels",
            )
        return apply_classification_fallback(result, self._fallback_policy)

    def _first_matching_result(self, request: ClassificationRequest) -> ClassificationResult:
        normalized_text = request.text.casefold()
        for rule in self._rules:
            if _matches_rule(normalized_text, rule):
                return ClassificationResult(
                    label=rule.label,
                    confidence=rule.confidence,
                    reason=rule.reason,
                    model_metadata=self._metadata_for_slot(request.model_slot),
                    latency_ms=0.0,
                )
        return self._unknown_result(request, reason="no classification rule matched")

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
            provider="rule",
            model_name=self._model,
            adapter_name="rule_based_text_classifier",
            model_slot=model_slot,
        )


def _matches_rule(normalized_text: str, rule: ClassificationRule) -> bool:
    return any(keyword.casefold() in normalized_text for keyword in rule.keywords)


def _label_allowed(label: str, candidate_labels: tuple[str, ...]) -> bool:
    return not candidate_labels or label in candidate_labels
