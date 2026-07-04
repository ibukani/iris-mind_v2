"""小型分類器 contract tests。"""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from iris.contracts.classification import (
    ClassificationFallbackPolicy,
    ClassificationRequest,
    ClassificationResult,
    apply_classification_fallback,
)
from iris.contracts.model_invocation import ModelInvocationMetadata
from iris.contracts.model_policy import ModelCallKind
from tests.helpers.approx import approx


def test_classification_result_exposes_required_metadata() -> None:
    """分類結果は label/confidence/reason/model metadata/latency を保持する。"""
    result = ClassificationResult(
        label="intent.chat",
        confidence=0.91,
        reason="keyword rule matched",
        model_metadata=_classifier_metadata(),
        latency_ms=12.5,
    )

    assert result.label == "intent.chat"
    assert result.confidence == approx(0.91)
    assert result.reason == "keyword rule matched"
    assert result.model_metadata.call_kind is ModelCallKind.SMALL_CLASSIFIER
    assert result.model_metadata.provider == "rule"
    assert result.latency_ms == approx(12.5)


def test_classification_result_validates_label_confidence_and_latency() -> None:
    """空 label、不正 confidence、不正 latency は境界で拒否される。"""
    with pytest.raises(ValidationError):
        ClassificationResult(
            label=" ",
            confidence=0.5,
            reason="invalid label",
            model_metadata=_classifier_metadata(),
        )

    with pytest.raises(ValidationError):
        ClassificationResult(
            label="intent.chat",
            confidence=1.01,
            reason="invalid confidence",
            model_metadata=_classifier_metadata(),
        )

    with pytest.raises(ValidationError):
        ClassificationResult(
            label="intent.chat",
            confidence=0.5,
            reason="invalid latency",
            model_metadata=_classifier_metadata(),
            latency_ms=-1.0,
        )


def test_low_confidence_fallback_preserves_original_label() -> None:
    """低信頼 result は unknown に正規化され、元 label が残る。"""
    result = ClassificationResult(
        label="intent.risky",
        confidence=0.4,
        reason="weak evidence",
        model_metadata=_classifier_metadata(),
        latency_ms=3.0,
    )

    fallback = apply_classification_fallback(
        result,
        ClassificationFallbackPolicy(confidence_threshold=0.7, unknown_label="unknown"),
    )

    assert fallback.label == "unknown"
    assert fallback.confidence == approx(0.4)
    assert fallback.reason == "classification confidence below threshold"
    assert fallback.fallback_applied is True
    assert fallback.original_label == "intent.risky"
    assert fallback.latency_ms == approx(3.0)


def test_confident_classification_bypasses_fallback() -> None:
    """閾値以上の result はそのまま返る。"""
    result = ClassificationResult(
        label="intent.chat",
        confidence=0.9,
        reason="strong evidence",
        model_metadata=_classifier_metadata(),
    )

    assert apply_classification_fallback(result, ClassificationFallbackPolicy()) is result


def test_classification_request_keeps_candidate_labels_and_safe_metadata() -> None:
    """Request は候補 label と安全 metadata だけを保持する。"""
    request = ClassificationRequest(
        text="hello",
        candidate_labels=("intent.chat", "unknown"),
        model_slot="fast_judge",
        metadata={"feature": "high_risk_context"},
    )

    assert request.candidate_labels == ("intent.chat", "unknown")
    assert request.model_slot == "fast_judge"
    assert request.metadata == {"feature": "high_risk_context"}


def _classifier_metadata() -> ModelInvocationMetadata:
    return ModelInvocationMetadata(
        call_kind=ModelCallKind.SMALL_CLASSIFIER,
        provider="rule",
        model_name="rule-v1",
        adapter_name="rule_based_text_classifier",
        model_slot="fast_judge",
    )
