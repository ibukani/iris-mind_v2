# Copyright 2025 Iris Mind
"""Tests for proactive idle tick flow with salience-based action selection."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.contracts.observations import IdleTickObservation, ObservationKind
from iris.core.ids import ObservationId, SessionId
from iris.runtime.app import IrisApp
from iris.runtime.wiring.features import wire_proactive_talk_cognitive_cycle


def _idle_tick(idle_seconds: float) -> IdleTickObservation:
    """Return an IdleTickObservation with the given idle duration."""
    return IdleTickObservation(
        observation_id=ObservationId("obs-proactive-idle-flow"),
        session_id=SessionId("session-proactive-idle-flow"),
        actor=None,
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.IDLE_TICK,
        reason="test_idle",
        idle_seconds=idle_seconds,
    )


@pytest.mark.anyio
async def test_low_idle_tick_flow_selects_no_action() -> None:
    """Verify a low idle tick duration produces a no_action plan."""
    cycle = wire_proactive_talk_cognitive_cycle()
    result = await cycle.run(_idle_tick(10.0))

    assert result.selected_plan.turn_intent == "no_action"
    assert result.selected_plan.should_respond is False
    assert result.selected_plan.candidate_text is None


@pytest.mark.anyio
async def test_high_idle_tick_flow_represents_proactive_talk_without_sending() -> None:
    """Verify a high idle tick duration produces proactive_talk without sending."""
    app = IrisApp(cycle=wire_proactive_talk_cognitive_cycle())

    output = await app.process_observation(_idle_tick(600.0))

    assert output.text is None
    assert output.priority == 70
