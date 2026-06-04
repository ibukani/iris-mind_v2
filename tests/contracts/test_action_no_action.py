"""ActionPlanのno-actionセマンティクスとPresentedOutputのsendableプロパティのテスト。"""

from __future__ import annotations

import pytest

from iris.contracts.actions import ActionPlan, PresentedOutput
from tests.helpers.immutability import assert_frozen_field

_ERR_INVALID_NO_ACTION = "no_action plan must not include candidate text or response intent"


def test_canonical_no_action_plan_is_identified() -> None:
    """標準的なno_actionプランが正しく識別されることを確認する。"""
    plan = ActionPlan(
        turn_intent="no_action",
        candidate_text=None,
        should_respond=False,
        priority=0,
    )
    assert plan.is_no_action is True
    assert plan.turn_intent == "no_action"
    assert plan.should_respond is False


def test_no_action_plan_with_text_is_rejected() -> None:
    """no_actionプランが送信用テキストを持てないことを確認する。"""
    with pytest.raises(ValueError, match=_ERR_INVALID_NO_ACTION):
        ActionPlan(
            turn_intent="no_action",
            candidate_text="unexpected",
            should_respond=False,
            priority=0,
        )


def test_no_action_plan_with_should_respond_is_rejected() -> None:
    """no_actionプランが応答意図を持てないことを確認する。"""
    with pytest.raises(ValueError, match=_ERR_INVALID_NO_ACTION):
        ActionPlan(
            turn_intent="no_action",
            candidate_text=None,
            should_respond=True,
            priority=0,
        )


def test_proactive_talk_plan_is_not_no_action() -> None:
    """proactive_talkプランがno_actionとして識別されないことを確認する。"""
    plan = ActionPlan(
        turn_intent="proactive_talk",
        candidate_text=None,
        should_respond=True,
        priority=70,
    )
    assert plan.is_no_action is False


def test_response_plan_is_not_no_action() -> None:
    """respondプランがno_actionとして識別されないことを確認する。"""
    plan = ActionPlan(
        turn_intent="respond",
        candidate_text="hello",
        should_respond=True,
        priority=10,
    )
    assert plan.is_no_action is False


def test_fallback_plan_is_no_action() -> None:
    """フォールバックのno_actionプランが正しく識別されることを確認する。"""
    plan = ActionPlan(
        turn_intent="no_action",
        candidate_text=None,
        should_respond=False,
        priority=-1,
    )
    assert plan.is_no_action is True


def test_presented_output_is_sendable_when_has_text() -> None:
    """textが空ではない場合にPresentedOutput.is_sendableがTrueであることを確認する。"""
    output = PresentedOutput(text="hello")
    assert output.is_sendable is True


def test_presented_output_is_not_sendable_when_text_is_none() -> None:
    """textがNoneの場合にPresentedOutput.is_sendableがFalseであることを確認する。"""
    output = PresentedOutput(text=None)
    assert output.is_sendable is False


def test_presented_output_is_not_sendable_when_text_is_empty() -> None:
    """textが空文字の場合にPresentedOutput.is_sendableがFalseであることを確認する。"""
    output = PresentedOutput(text="")
    assert output.is_sendable is False


def test_presented_output_is_not_sendable_when_text_is_whitespace() -> None:
    """textが空白のみの場合にPresentedOutput.is_sendableがFalseであることを確認する。"""
    output = PresentedOutput(text="   \n\t")
    assert output.is_sendable is False


def test_action_plan_is_immutable() -> None:
    """ActionPlanが作成後に変更できないことを確認する。"""
    plan = ActionPlan(
        turn_intent="no_action",
        candidate_text=None,
        should_respond=False,
        priority=0,
    )
    assert_frozen_field(plan, "turn_intent", "other")


def test_presented_output_is_immutable() -> None:
    """PresentedOutputが作成後に変更できないことを確認する。"""
    output = PresentedOutput(text="hello")
    assert_frozen_field(output, "text", "other")
