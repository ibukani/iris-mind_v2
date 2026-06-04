"""Tests for proactive talk goal proposal and action selection."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.cognitive.workspace.frame import WorkspaceFrame
from iris.contracts.observations import IdleTickObservation, ObservationKind
from iris.core.ids import ObservationId, SessionId
from iris.features.proactive_talk.definition import ProactiveActionSelectionStep
from iris.features.proactive_talk.goals import GoalProposer
from iris.features.proactive_talk.models import ProactiveSalience


def _idle_frame(idle_seconds: float) -> WorkspaceFrame:
    """Return a WorkspaceFrame with an IdleTickObservation."""
    return WorkspaceFrame(
        observation=IdleTickObservation(
            observation_id=ObservationId("obs-proactive-goal"),
            session_id=SessionId("session-proactive-goal"),
            actor=None,
            space_id=None,
            occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
            kind=ObservationKind.IDLE_TICK,
            idle_seconds=idle_seconds,
        )
    )


def test_low_salience_proposes_no_action() -> None:
    """Verify a low salience score produces a no_action goal."""
    goal = GoalProposer().propose(ProactiveSalience(score=0.1, threshold=0.5))

    assert goal.name == "no_action"
    assert goal.should_speak is False
    assert goal.priority == 0


def test_high_salience_proposes_proactive_talk() -> None:
    """Verify a high salience score produces a proactive_talk goal."""
    goal = GoalProposer().propose(ProactiveSalience(score=0.7, threshold=0.5))

    assert goal.name == "proactive_talk"
    assert goal.should_speak is True
    assert goal.priority == 70


@pytest.mark.anyio
async def test_proactive_action_selection_returns_typed_action_plan() -> None:
    """Verify ProactiveActionSelectionStep returns an ActionPlan with proactive_talk intent."""
    result = await ProactiveActionSelectionStep().run(_idle_frame(600.0))

    assert result.action_plans[0].turn_intent == "proactive_talk"
    assert result.action_plans[0].candidate_text is None
    assert result.action_plans[0].should_respond is True
