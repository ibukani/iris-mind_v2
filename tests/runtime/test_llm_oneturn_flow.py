"""Tests for LLM-backed one-turn cognitive flow with safety gates."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.contracts.observations import ObservationKind, UserMessageObservation
from iris.core.ids import ObservationId, SessionId
from iris.runtime.app import IrisApp
from iris.runtime.wiring.cognitive import wire_text_response_cognitive_cycle
from iris.safety.action_gate import GateDecision, SafetyDecision

if TYPE_CHECKING:
    from iris.contracts.actions import ActionPlan, PresentedOutput


class BlockingActionGate:
    """Stub action safety gate that blocks all plans."""

    async def check_plan(self, plan: ActionPlan) -> SafetyDecision:  # noqa: PLR6301, ARG002 -- test stub implements ActionSafetyGate protocol; self/plan are unused by stub design
        """Return a BLOCK decision."""
        return SafetyDecision(decision=GateDecision.BLOCK, reason="blocked action")


class BlockingOutputGate:
    """Stub output safety gate that blocks all outputs."""

    async def check_output(self, output: PresentedOutput) -> SafetyDecision:  # noqa: PLR6301, ARG002 -- test stub implements OutputSafetyGate protocol; self/output are unused by stub design
        """Return a BLOCK decision."""
        return SafetyDecision(decision=GateDecision.BLOCK, reason="blocked output")


def user_message(text: str = "hello") -> UserMessageObservation:
    """Return a UserMessageObservation with the given text."""
    return UserMessageObservation(
        observation_id=ObservationId("obs-runtime"),
        session_id=SessionId("session-runtime"),
        actor=None,
        space_id=None,
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.USER_MESSAGE,
        text=text,
    )


@pytest.mark.anyio
async def test_one_turn_flow_uses_fake_llm_and_returns_presented_output() -> None:
    """Verify LLM-backed one-turn flow returns a PresentedOutput with LLM text."""
    llm = FakeLLMClient(responses=("llm-backed reply",))
    app = IrisApp(cycle=wire_text_response_cognitive_cycle(llm))

    output = await app.process_observation(user_message("hello Iris"))

    assert output.text == "llm-backed reply"
    assert output.priority == 10
    assert llm.requests[0].messages[-1].content == "hello Iris"


@pytest.mark.anyio
async def test_action_safety_gate_blocks_llm_action_plan() -> None:
    """Verify a blocking action safety gate prevents LLM action from being presented."""
    llm = FakeLLMClient(responses=("unsafe reply",))
    app = IrisApp(
        cycle=wire_text_response_cognitive_cycle(llm),
        action_safety_gate=BlockingActionGate(),
    )

    output = await app.process_observation(user_message())

    assert output.text is None


@pytest.mark.anyio
async def test_output_safety_gate_blocks_llm_presented_output() -> None:
    """Verify a blocking output safety gate prevents LLM output from being sent."""
    llm = FakeLLMClient(responses=("blocked presented output",))
    app = IrisApp(
        cycle=wire_text_response_cognitive_cycle(llm),
        output_safety_gate=BlockingOutputGate(),
    )

    output = await app.process_observation(user_message())

    assert output.text is None
