"""Presentation hints contract tests."""

from __future__ import annotations

import pytest

from iris.contracts.actions import PresentedOutput, send_message_action_from_output
from iris.contracts.presentation import PresentationHints, PresentationModality
from iris.core.ids import ActionId, CorrelationId, SessionId
from tests.helpers.immutability import assert_frozen_field


def test_presentation_hints_have_safe_unknown_defaults() -> None:
    """省略したmodalityとtimingが決定的な安全defaultになる。"""
    hints = PresentationHints()

    assert hints.modality is PresentationModality.UNKNOWN
    assert hints.delay_ms == 0
    assert hints.priority == 0
    assert hints.interruptible is True


def test_presentation_hints_are_immutable_and_validate_delay() -> None:
    """Hintsが不変で、負のdelayを拒否する。"""
    hints = PresentationHints()
    assert_frozen_field(hints, "modality", PresentationModality.TEXT)

    with pytest.raises(ValueError, match="greater than or equal to 0"):
        PresentationHints(delay_ms=-1)


def test_send_message_action_mapper_preserves_only_presentation_hints() -> None:
    """正本mapperがhintだけを搬送し、安全metadataを混入させない。"""
    hints = PresentationHints(
        style_hint="calm",
        emotion_hint="warm",
        expression_hint="smile",
        delay_ms=20,
        priority=4,
        interruptible=False,
        modality=PresentationModality.BOTH,
    )
    output = PresentedOutput(
        text="hello",
        presentation_hints=hints,
        safety_block_reason=None,
        policy_constraint_names=("delivery_policy",),
    )

    action = send_message_action_from_output(
        output,
        action_id=ActionId("action-1"),
        session_id=SessionId("session-1"),
        correlation_id=CorrelationId("correlation-1"),
    )

    assert action.presentation_hints == hints
    assert action.text == "hello"
    assert "safety_block_reason" not in action.model_dump()
    assert "policy_constraint_names" not in action.model_dump()


def test_send_message_action_mapper_rejects_safety_blocked_output() -> None:
    """Safety block済みoutputがtextを持っていても外部actionにならない。"""
    output = PresentedOutput(
        text="must not send",
        safety_block_reason="output_safety_blocked",
    )

    with pytest.raises(ValueError, match="sendable PresentedOutput required"):
        send_message_action_from_output(
            output,
            action_id=ActionId("action-blocked"),
            session_id=SessionId("session-blocked"),
            correlation_id=CorrelationId("correlation-blocked"),
        )
