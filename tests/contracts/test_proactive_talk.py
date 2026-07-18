"""Proactive generation contract tests."""

from __future__ import annotations

import math

from pydantic import ValidationError
import pytest

from iris.contracts.proactive_talk import (
    ProactiveTalkContext,
    ProactiveTalkPrompt,
)


def test_proactive_context_rejects_unbounded_items() -> None:
    """Prompt context item は bounded でなければならない。"""
    with pytest.raises(ValidationError):
        ProactiveTalkContext(
            idle_seconds=600.0,
            memory_summaries=("x" * 241,),
        )


def test_proactive_prompt_has_typed_bounded_instruction() -> None:
    """Proactive prompt は typed context と instruction を持つ。"""
    prompt = ProactiveTalkPrompt(
        context=ProactiveTalkContext(idle_seconds=600.0),
        instruction="Write one short message.",
    )

    assert math.isclose(prompt.context.idle_seconds, 600.0)
    assert prompt.instruction == "Write one short message."
