"""モデル呼び出し cascade policy 契約テスト。"""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from iris.contracts.model_policy import (
    CascadeDecision,
    CascadeFallbackBehavior,
    CascadeResult,
    ModelCallDescriptor,
    ModelCallKind,
    ModelCallSite,
)
from iris.core.metadata import immutable_metadata


def test_model_call_descriptor_keeps_safe_metadata_only() -> None:
    """ModelCallDescriptor は prompt ではなく安全なモデルメタデータを保持する。"""
    descriptor = ModelCallDescriptor(
        call_kind=ModelCallKind.LARGE_LLM,
        call_site=ModelCallSite.USER_RESPONSE_HOT_PATH,
        model_slot="default_chat",
        model_name="fake-llm",
        metadata=immutable_metadata({"provider": "fake", "model": "fake-llm"}),
    )

    assert descriptor.call_kind is ModelCallKind.LARGE_LLM
    assert descriptor.call_site is ModelCallSite.USER_RESPONSE_HOT_PATH
    assert descriptor.metadata == {"provider": "fake", "model": "fake-llm"}


def test_cascade_result_exposes_reason_confidence_and_metadata() -> None:
    """CascadeResult は #88 が要求する reason / confidence / model metadata を持つ。"""
    result = CascadeResult(
        decision=CascadeDecision.FALLBACK,
        reason="model call budget exceeded",
        confidence=0.42,
        fallback_behavior=CascadeFallbackBehavior.DETERMINISTIC_BASELINE,
        model_metadata=immutable_metadata({"model_slot": "default_chat"}),
    )

    assert not result.accepted
    assert result.reason == "model call budget exceeded"
    assert abs(result.confidence - 0.42) < 1e-9
    assert result.fallback_behavior is CascadeFallbackBehavior.DETERMINISTIC_BASELINE
    assert result.model_metadata == {"model_slot": "default_chat"}


def test_cascade_confidence_is_probability() -> None:
    """Cascade confidence は 0.0 から 1.0 の範囲に制限される。"""
    with pytest.raises(ValidationError):
        CascadeResult(
            decision=CascadeDecision.ACCEPT,
            reason="invalid",
            confidence=1.1,
        )

    with pytest.raises(ValidationError):
        ModelCallDescriptor(
            call_kind=ModelCallKind.LARGE_LLM,
            call_site=ModelCallSite.USER_RESPONSE_HOT_PATH,
            confidence=-0.1,
        )
