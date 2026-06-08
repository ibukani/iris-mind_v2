"""Tests for the presentation layer."""

from __future__ import annotations

import pytest

from iris.contracts.actions import ActionPlan
from iris.presentation.presenter import SimplePresenter


@pytest.mark.anyio
async def test_simple_presenter_returns_text_for_action_plan() -> None:
    """SimplePresenter returns candidate_text for a normal action plan."""
    presenter = SimplePresenter()
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
async def test_simple_presenter_returns_none_for_no_action() -> None:
    """SimplePresenter returns None text for a no-action plan."""
    presenter = SimplePresenter()
    plan = ActionPlan(
        turn_intent="no_action",
        candidate_text=None,
        should_respond=False,
        priority=-1,
    )
    output = await presenter.present(plan)
    assert output.text is None
