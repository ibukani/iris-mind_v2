"""Tests for the cognitive cycle service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import PerceptionResult, PipelineStepResult, StepStatus
from iris.cognitive.cycle.service import CognitiveCycle
from iris.cognitive.workspace.frame import WorkspaceFrame
from iris.contracts.actions import ActionPlan
from iris.contracts.observations import ActorMessageObservation, ObservationContext, ObservationKind
from iris.core.ids import ObservationId, SessionId
from tests.helpers.private_access import get_private_attr_matching, is_callable


def _observation(text: str) -> ActorMessageObservation:
    """Build a simple actor message observation.

    Returns:
        ActorMessageObservation: Observation with the given text.
    """
    return ActorMessageObservation(
        observation_id=ObservationId("obs-1"),
        session_id=SessionId("session-1"),
        context=ObservationContext(),
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
    )


class _DummyStep:
    """Dummy pipeline step that returns a fixed result."""

    name = "dummy"

    def __init__(self, result: PipelineStepResult) -> None:
        self._result = result

    async def run(self, frame: WorkspaceFrame) -> PipelineStepResult:
        """Return the pre-configured result."""
        _ = frame
        return self._result


def test_select_action_plan_returns_first_when_only_one() -> None:
    """_select_action_plan returns the only plan when there's just one."""
    plan = ActionPlan(
        turn_intent="respond",
        candidate_text="hi",
        should_respond=True,
        priority=1,
    )
    cycle = CognitiveCycle(
        steps=(),
        frame_builder=FrameBuilder(),
        fallback_plan=ActionPlan(
            turn_intent="no_action",
            candidate_text=None,
            should_respond=False,
            priority=-1,
        ),
    )
    frame = WorkspaceFrame(
        observation=_observation("test"),
        candidate_action_plans=(plan,),
    )
    select_action: Any = get_private_attr_matching(cycle, "_select_action_plan", is_callable)
    selected = select_action(frame)
    assert selected is plan


def test_select_action_plan_returns_fallback_when_empty() -> None:
    """_select_action_plan returns fallback when no plans are present."""
    fallback = ActionPlan(
        turn_intent="no_action",
        candidate_text=None,
        should_respond=False,
        priority=-1,
    )
    cycle = CognitiveCycle(
        steps=(),
        frame_builder=FrameBuilder(),
        fallback_plan=fallback,
    )
    frame = WorkspaceFrame(observation=_observation("test"))
    select_action: Any = get_private_attr_matching(cycle, "_select_action_plan", is_callable)
    selected = select_action(frame)
    assert selected is fallback


def test_select_action_plan_prefers_higher_priority() -> None:
    """_select_action_plan selects the plan with highest priority."""
    low = ActionPlan(
        turn_intent="respond",
        candidate_text="low",
        should_respond=True,
        priority=1,
    )
    high = ActionPlan(
        turn_intent="respond",
        candidate_text="high",
        should_respond=True,
        priority=5,
    )
    mid = ActionPlan(
        turn_intent="respond",
        candidate_text="mid",
        should_respond=True,
        priority=3,
    )
    cycle = CognitiveCycle(
        steps=(),
        frame_builder=FrameBuilder(),
        fallback_plan=ActionPlan(
            turn_intent="no_action",
            candidate_text=None,
            should_respond=False,
            priority=-1,
        ),
    )
    frame = WorkspaceFrame(
        observation=_observation("test"),
        candidate_action_plans=(low, high, mid),
    )
    select_action: Any = get_private_attr_matching(cycle, "_select_action_plan", is_callable)
    selected = select_action(frame)
    assert selected is high


@pytest.mark.anyio
async def test_run_executes_steps_in_order() -> None:
    """CognitiveCycle.run executes steps in order and applies results to frame."""
    step1 = _DummyStep(
        PerceptionResult(step_name="p1", status=StepStatus.OK, text="hello", language="en")
    )
    step2 = _DummyStep(
        PerceptionResult(step_name="p2", status=StepStatus.OK, text="world", language="en")
    )
    cycle = CognitiveCycle(
        steps=(step1, step2),
        frame_builder=FrameBuilder(),
        fallback_plan=ActionPlan(
            turn_intent="no_action",
            candidate_text=None,
            should_respond=False,
            priority=-1,
        ),
    )
    result = await cycle.run(_observation("test"))
    assert result.frame.interpreted_input is not None
    assert result.frame.interpreted_input.text == "world"
