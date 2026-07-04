"""Typed safety context contract tests。"""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from iris.contracts.actions import PresentedOutput, presented_output_with_policy_metadata
from iris.contracts.policy import PolicyConstraint
from iris.contracts.safety import (
    SafetyContext,
    SafetyContextCategory,
    SafetyContextReason,
    SafetyContextSeverity,
    SafetyContextSource,
    SafetyResponseDirective,
)


def _context() -> SafetyContext:
    return SafetyContext(
        category=SafetyContextCategory.SELF_HARM,
        severity=SafetyContextSeverity.HIGH,
        source=SafetyContextSource.USER_INITIATED,
        confidence=0.9,
        reasons=(
            SafetyContextReason(
                code="self_harm_support_signal",
                description="Static support signal metadata.",
            ),
        ),
        directive=SafetyResponseDirective.ALLOW_SUPPORT,
    )


def test_policy_constraint_can_carry_typed_safety_context() -> None:
    """PolicyConstraint は typed safety context を保持できる。"""
    context = _context()
    constraint = PolicyConstraint(
        name="sensitive_safety_context",
        reason="typed metadata",
        safety_context=context,
    )

    assert constraint.safety_context == context
    safety_context = constraint.safety_context
    assert safety_context is not None
    assert safety_context.reasons[0].code == "self_harm_support_signal"


def test_safety_context_confidence_is_bounded() -> None:
    """SafetyContext confidence は 0.0 から 1.0 に制限される。"""
    with pytest.raises(ValidationError):
        SafetyContext(
            category=SafetyContextCategory.SELF_HARM,
            severity=SafetyContextSeverity.HIGH,
            source=SafetyContextSource.USER_INITIATED,
            confidence=1.1,
            reasons=(SafetyContextReason(code="code", description="description"),),
            directive=SafetyResponseDirective.ALLOW_SUPPORT,
        )


def test_safety_context_requires_reason_metadata() -> None:
    """SafetyContext は observability 用の reason metadata を必ず持つ。"""
    with pytest.raises(ValidationError):
        SafetyContext(
            category=SafetyContextCategory.UNKNOWN_HIGH_RISK,
            severity=SafetyContextSeverity.HIGH,
            source=SafetyContextSource.USER_INITIATED,
            confidence=0.5,
            reasons=(),
            directive=SafetyResponseDirective.BLOCK,
        )


def test_presented_output_policy_metadata_preserves_safety_contexts() -> None:
    """PresentedOutput へ constraint 名と safety context metadata を伝搬できる。"""
    context = _context()
    merged = presented_output_with_policy_metadata(
        PresentedOutput(text="hello"),
        constraint_names=("sensitive_safety_context",),
        safety_contexts=(context,),
    )

    assert merged.policy_constraint_names == ("sensitive_safety_context",)
    assert merged.safety_contexts == (context,)
