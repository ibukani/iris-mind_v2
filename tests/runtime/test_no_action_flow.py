from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.contracts.actions import ActionPlan, PresentedOutput
from iris.contracts.observations import IdleTickObservation, ObservationKind
from iris.core.ids import ObservationId, SessionId
from iris.runtime.app import IrisApp
from iris.runtime.wiring.features import wire_proactive_talk_cognitive_cycle


class FailingPresenter:
    async def present(self, plan: ActionPlan) -> PresentedOutput:
        raise AssertionError("presenter should not be called for no_action")


class SpyPresenter:
    def __init__(self) -> None:
        self.calls: list[ActionPlan] = []

    async def present(self, plan: ActionPlan) -> PresentedOutput:
        self.calls.append(plan)
        return PresentedOutput(text=plan.candidate_text, priority=plan.priority)


def _idle_tick(idle_seconds: float) -> IdleTickObservation:
    return IdleTickObservation(
        observation_id=ObservationId("obs-no-action-flow"),
        session_id=SessionId("session-no-action-flow"),
        actor=None,
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.IDLE_TICK,
        reason="test",
        idle_seconds=idle_seconds,
    )


@pytest.mark.anyio
async def test_no_action_skips_presenter() -> None:
    app = IrisApp(
        cycle=wire_proactive_talk_cognitive_cycle(),
        presenter=FailingPresenter(),
    )
    output = await app.process_observation(_idle_tick(10.0))
    assert output.text is None


@pytest.mark.anyio
async def test_no_action_returns_non_sendable_output() -> None:
    app = IrisApp(cycle=wire_proactive_talk_cognitive_cycle())
    output = await app.process_observation(_idle_tick(10.0))
    assert output.is_sendable is False
    assert output.text is None


@pytest.mark.anyio
async def test_proactive_speak_calls_presenter() -> None:
    spy = SpyPresenter()
    app = IrisApp(cycle=wire_proactive_talk_cognitive_cycle(), presenter=spy)
    output = await app.process_observation(_idle_tick(600.0))
    assert len(spy.calls) == 1
    called_plan = spy.calls[0]
    assert called_plan.turn_intent == "proactive_talk"
    assert output.text is None


@pytest.mark.anyio
async def test_no_action_does_not_produce_user_visible_text() -> None:
    app = IrisApp(cycle=wire_proactive_talk_cognitive_cycle())
    output = await app.process_observation(_idle_tick(10.0))
    assert output.text is None
    assert output.is_sendable is False
    assert isinstance(output, PresentedOutput)


@pytest.mark.anyio
async def test_low_salience_proactive_produces_no_action() -> None:
    cycle = wire_proactive_talk_cognitive_cycle()
    result = await cycle.run(_idle_tick(10.0))
    plan = result.selected_plan
    assert plan.is_no_action is True
    assert plan.turn_intent == "no_action"
    assert plan.should_respond is False
    assert plan.candidate_text is None


@pytest.mark.anyio
async def test_fallback_plan_is_no_action_and_skips_presenter() -> None:
    from iris.cognitive.cycle.frame_builder import FrameBuilder
    from iris.cognitive.cycle.service import CognitiveCycle
    from iris.contracts.actions import ActionPlan

    cycle = CognitiveCycle(
        steps=(),
        frame_builder=FrameBuilder(),
        fallback_plan=ActionPlan(turn_intent="no_action", candidate_text=None, should_respond=False, priority=-1),
    )
    app = IrisApp(cycle=cycle, presenter=FailingPresenter())
    output = await app.process_observation(_idle_tick(10.0))
    assert output.is_sendable is False
    assert output.text is None
