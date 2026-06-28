# Copyright 2025 Iris Mind
"""Tests for no-action flow and proactive talk fallback behavior."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.service import CognitiveCycle
from iris.contracts.actions import ActionPlan, PresentedOutput
from iris.contracts.observations import IdleTickObservation, ObservationContext, ObservationKind
from iris.core.ids import ObservationId, SessionId
from iris.runtime.app import IrisApp
from iris.runtime.wiring.features import wire_proactive_talk_cognitive_cycle
from tests.helpers.output_pipeline import make_output_pipeline


class FailingPresenter:
    """意図的に失敗するPresenter。"""

    def can_present(self, plan: ActionPlan) -> bool:
        _ = plan
        return True

    async def present(self, plan: ActionPlan) -> PresentedOutput:
        """Raise an error to verify presenter is not invoked.

        Raises:
            AssertionError: 常に呼び出しを検証するために発生。
        """
        _ = self, plan
        msg = "presenter should not be called for no_action"
        raise AssertionError(msg)


class SpyPresenter:
    """プレゼンテーション呼び出しを記録する。"""

    def __init__(self) -> None:
        """Initialize empty call log."""
        self.calls: list[ActionPlan] = []

    def can_present(self, plan: ActionPlan) -> bool:
        _ = plan
        return True

    async def present(self, plan: ActionPlan) -> PresentedOutput:
        """Record the plan and return a PresentedOutput.

        Returns:
            PresentedOutput: 記録されたプランに基づく出力。
        """
        self.calls.append(plan)
        return PresentedOutput(text=plan.candidate_text, priority=plan.priority)


def _idle_tick(idle_seconds: float) -> IdleTickObservation:
    """Return an IdleTickObservation with the given idle duration."""
    return IdleTickObservation(
        observation_id=ObservationId("obs-no-action-flow"),
        session_id=SessionId("session-no-action-flow"),
        context=ObservationContext(),
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.IDLE_TICK,
        reason="test",
        idle_seconds=idle_seconds,
    )


@pytest.mark.anyio
async def test_no_action_skips_presenter() -> None:
    """Verify the presenter is not called for a no_action plan."""
    app = IrisApp(
        cycle=wire_proactive_talk_cognitive_cycle(),
        output_pipeline=make_output_pipeline(presenter=FailingPresenter()),
    )
    output = await app.process_observation(_idle_tick(10.0))
    assert output.text is None


@pytest.mark.anyio
async def test_no_action_returns_non_sendable_output() -> None:
    """Verify a no_action flow returns a non-sendable PresentedOutput."""
    app = IrisApp(
        output_pipeline=make_output_pipeline(),
        cycle=wire_proactive_talk_cognitive_cycle(),
    )
    output = await app.process_observation(_idle_tick(10.0))
    assert output.is_sendable is False
    assert output.text is None


@pytest.mark.anyio
async def test_proactive_speak_calls_presenter() -> None:
    """Verify the presenter is called for a proactive_talk plan."""
    spy = SpyPresenter()
    app = IrisApp(
        cycle=wire_proactive_talk_cognitive_cycle(),
        output_pipeline=make_output_pipeline(presenter=spy),
    )
    output = await app.process_observation(_idle_tick(600.0))
    assert len(spy.calls) == 1
    called_plan = spy.calls[0]
    assert called_plan.turn_intent == "proactive_talk"
    assert output.text is None


@pytest.mark.anyio
async def test_no_action_does_not_produce_actor_visible_text() -> None:
    """Verify no_action produces PresentedOutput with text=None and is_sendable=False."""
    app = IrisApp(
        output_pipeline=make_output_pipeline(),
        cycle=wire_proactive_talk_cognitive_cycle(),
    )
    output = await app.process_observation(_idle_tick(10.0))
    assert output.text is None
    assert output.is_sendable is False
    assert isinstance(output, PresentedOutput)


@pytest.mark.anyio
async def test_low_salience_proactive_produces_no_action() -> None:
    """Verify low salience proactive flow produces a no_action plan."""
    cycle = wire_proactive_talk_cognitive_cycle()
    result = await cycle.run(_idle_tick(10.0))
    plan = result.selected_plan
    assert plan.is_no_action is True
    assert plan.turn_intent == "no_action"
    assert plan.should_respond is False
    assert plan.candidate_text is None


@pytest.mark.anyio
async def test_fallback_plan_is_no_action_and_skips_presenter() -> None:
    """Verify CognitiveCycle fallback plan produces no_action and skips presenter."""
    cycle = CognitiveCycle(
        steps=(),
        frame_builder=FrameBuilder(),
        fallback_plan=ActionPlan(
            turn_intent="no_action", candidate_text=None, should_respond=False, priority=-1
        ),
    )
    app = IrisApp(
        cycle=cycle,
        output_pipeline=make_output_pipeline(presenter=FailingPresenter()),
    )
    output = await app.process_observation(_idle_tick(10.0))
    assert output.is_sendable is False
    assert output.text is None
