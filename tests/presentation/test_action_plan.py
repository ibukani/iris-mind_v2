"""DefaultActionPlanPresenter のテスト。"""

from __future__ import annotations

import pytest

from iris.contracts.actions import ActionPlan
from iris.presentation.action_plan import DefaultActionPlanPresenter


@pytest.mark.anyio
async def test_default_action_plan_presenter_returns_text_for_action_plan() -> None:
    """DefaultActionPlanPresenter は通常 ActionPlan の text を提示する。"""
    presenter = DefaultActionPlanPresenter()
    plan = ActionPlan(
        turn_intent="respond",
        candidate_text="Hello!",
        should_respond=True,
        priority=1,
    )
    output = await presenter.present(plan)
    assert output.text == "Hello!"
    assert output.priority == 1
    assert output.interruptible is True


@pytest.mark.anyio
async def test_default_action_plan_presenter_returns_none_for_no_action() -> None:
    """DefaultActionPlanPresenter は no-action plan を no-send output に変換する。"""
    presenter = DefaultActionPlanPresenter()
    plan = ActionPlan(
        turn_intent="no_action",
        candidate_text=None,
        should_respond=False,
        priority=-1,
    )
    output = await presenter.present(plan)
    assert output.text is None


def test_default_action_plan_presenter_defers_event_reaction() -> None:
    """event_reaction は専用 presenter を優先するため default presenter は扱わない。"""
    presenter = DefaultActionPlanPresenter()
    plan = ActionPlan(
        turn_intent="event_reaction",
        candidate_text="nice!",
        should_respond=True,
        priority=1,
    )
    assert presenter.can_present(plan) is False
