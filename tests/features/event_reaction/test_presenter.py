"""Event reaction presentation tests."""

from __future__ import annotations

import pytest

from iris.contracts.actions import ActionPlan
from iris.features.event_reaction.presenter import EventReactionPresenter


@pytest.mark.asyncio
async def test_event_reaction_presenter_converts_candidate_to_output() -> None:
    """ActionPlanをPresentedOutputへ変換する。"""
    candidate = ActionPlan(
        turn_intent="event_reaction",
        candidate_text="Welcome back.",
        should_respond=True,
        priority=7,
        interruptible=False,
    )

    output = await EventReactionPresenter().present(candidate)

    assert output.text == "Welcome back."
    assert output.priority == 7
    assert output.interruptible is False
    assert output.style_hint == "event_reaction"
