"""Minimal one-turn cognitive runtime flow tests for v0.1.

Tests the end-to-end path:
  UserMessageObservation
  → CognitiveCycle (PerceptionStep → ActionSelectionStep)
  → ActionSafetyGate
  → SimplePresenter
  → OutputSafetyGate
  → PresentedOutput
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.cognitive.action.basic import SimpleActionSelectionStep
from iris.cognitive.perception.basic import SimplePerceptionStep
from iris.contracts.actions import ActionPlan, PresentedOutput
from iris.contracts.observations import ObservationKind, UserMessageObservation
from iris.core.ids import ObservationId, SessionId
from iris.runtime.app import IrisApp
from iris.safety.action_gate import GateDecision, SafetyDecision


@pytest.fixture
def app() -> IrisApp:
    return IrisApp(
        steps=[SimplePerceptionStep(), SimpleActionSelectionStep()],
    )


@pytest.fixture
def user_message() -> UserMessageObservation:
    return UserMessageObservation(
        observation_id=ObservationId("obs-1"),
        session_id=SessionId("session-1"),
        actor=None,
        occurred_at=datetime.now(UTC),
        kind=ObservationKind.USER_MESSAGE,
        text="Hello, Iris!",
    )


@pytest.mark.anyio
async def test_one_turn_flow_returns_presented_output(app: IrisApp, user_message: UserMessageObservation) -> None:
    result = await app.process_observation(user_message)
    assert isinstance(result, PresentedOutput)
    assert result.text == "Hello, Iris!"


@pytest.mark.anyio
async def test_one_turn_flow_with_empty_text_returns_presented_output(app: IrisApp) -> None:
    idle = UserMessageObservation(
        observation_id=ObservationId("obs-2"),
        session_id=SessionId("session-1"),
        actor=None,
        occurred_at=datetime.now(UTC),
        kind=ObservationKind.IDLE_TICK,
        text="",
    )
    result = await app.process_observation(idle)
    assert isinstance(result, PresentedOutput)


@pytest.mark.anyio
async def test_action_safety_gate_blocks(user_message: UserMessageObservation) -> None:
    class BlockingGate:
        async def check_plan(self, plan: ActionPlan) -> SafetyDecision:
            return SafetyDecision(decision=GateDecision.BLOCK, reason="test block")

    app = IrisApp(
        steps=[SimplePerceptionStep(), SimpleActionSelectionStep()],
        action_safety_gate=BlockingGate(),
    )
    result = await app.process_observation(user_message)
    assert isinstance(result, PresentedOutput)
    assert result.text is None


@pytest.mark.anyio
async def test_output_safety_gate_blocks(user_message: UserMessageObservation) -> None:
    class BlockingGate:
        async def check_output(self, output: PresentedOutput) -> SafetyDecision:
            return SafetyDecision(decision=GateDecision.BLOCK, reason="test block")

    app = IrisApp(
        steps=[SimplePerceptionStep(), SimpleActionSelectionStep()],
        output_safety_gate=BlockingGate(),
    )
    result = await app.process_observation(user_message)
    assert isinstance(result, PresentedOutput)
    assert result.text is None
