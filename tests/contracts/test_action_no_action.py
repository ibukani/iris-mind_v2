from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from iris.contracts.actions import ActionPlan, PresentedOutput


def test_canonical_no_action_plan_is_identified() -> None:
    plan = ActionPlan(
        turn_intent="no_action",
        candidate_text=None,
        should_respond=False,
        priority=0,
    )
    assert plan.is_no_action is True
    assert plan.turn_intent == "no_action"
    assert plan.should_respond is False


def test_proactive_talk_plan_is_not_no_action() -> None:
    plan = ActionPlan(
        turn_intent="proactive_talk",
        candidate_text=None,
        should_respond=True,
        priority=70,
    )
    assert plan.is_no_action is False


def test_response_plan_is_not_no_action() -> None:
    plan = ActionPlan(
        turn_intent="respond",
        candidate_text="hello",
        should_respond=True,
        priority=10,
    )
    assert plan.is_no_action is False


def test_fallback_plan_is_no_action() -> None:
    plan = ActionPlan(
        turn_intent="no_action",
        candidate_text=None,
        should_respond=False,
        priority=-1,
    )
    assert plan.is_no_action is True


def test_presented_output_is_sendable_when_has_text() -> None:
    output = PresentedOutput(text="hello")
    assert output.is_sendable is True


def test_presented_output_is_not_sendable_when_text_is_none() -> None:
    output = PresentedOutput(text=None)
    assert output.is_sendable is False


def test_action_plan_is_immutable() -> None:
    plan = ActionPlan(
        turn_intent="no_action",
        candidate_text=None,
        should_respond=False,
        priority=0,
    )
    with pytest.raises(FrozenInstanceError):
        plan.turn_intent = "other"


def test_presented_output_is_immutable() -> None:
    output = PresentedOutput(text="hello")
    with pytest.raises(FrozenInstanceError):
        output.text = "other"
