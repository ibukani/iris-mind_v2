"""ActivityEventReactionHandler boundary tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from iris.cognitive.workspace.frame import SituationContextSnapshot
from iris.contracts.actions import PresentedOutput
from iris.contracts.activity import ActivityKind
from iris.contracts.availability import AvailabilitySnapshot, AvailabilityStatus
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActivityEventObservation,
    ObservationContext,
    ObservationKind,
)
from iris.core.ids import ActorId, ExternalRef, ObservationId, SessionId
from iris.runtime.ingress.activity_event_reaction import ActivityEventReactionHandler
from iris.runtime.ingress.observation_ingress import (
    ObservationCapability,
    ObservationIngressContext,
)
from iris.runtime.ingress.observation_trust import ObservationTrustPolicy
from iris.safety.action_gate import GateDecision, SafetyDecision

_OCCURRED_AT = datetime(2026, 6, 24, 11, 0, tzinfo=UTC)


@pytest.mark.anyio
async def test_reaction_handler_does_not_react_when_trust_policy_rejects() -> None:
    """Missing REACT_TO_ACTIVITY capability never calls runner or output gate."""
    runner = _RecordingRunner(PresentedOutput(text="should not appear"))
    gate = _RecordingOutputGate(GateDecision.ALLOW)
    handler = ActivityEventReactionHandler(
        trust_policy=ObservationTrustPolicy(),
        runner=runner,
        output_gate=gate,
    )

    output = await handler.handle(
        _activity_observation(),
        _situation_context(),
        _ingress(ObservationCapability.INTEGRATE_ACTIVITY),
    )

    assert output == PresentedOutput(text=None)
    assert runner.calls == 0
    assert gate.checked == 0


@pytest.mark.anyio
async def test_reaction_handler_does_not_react_without_situation_context() -> None:
    """Missing situation context prevents runner and output gate calls."""
    runner = _RecordingRunner(PresentedOutput(text="should not appear"))
    gate = _RecordingOutputGate(GateDecision.ALLOW)
    handler = ActivityEventReactionHandler(
        trust_policy=ObservationTrustPolicy(),
        runner=runner,
        output_gate=gate,
    )

    output = await handler.handle(
        _activity_observation(),
        None,
        _ingress(ObservationCapability.REACT_TO_ACTIVITY),
    )

    assert output == PresentedOutput(text=None)
    assert runner.calls == 0
    assert gate.checked == 0


@pytest.mark.anyio
async def test_unauthenticated_ingress_blocks_reaction_even_with_capability() -> None:
    """Unauthenticated ingress with REACT_TO_ACTIVITY capability is still blocked."""
    runner = _RecordingRunner(PresentedOutput(text="should not appear"))
    gate = _RecordingOutputGate(GateDecision.ALLOW)
    handler = ActivityEventReactionHandler(
        trust_policy=ObservationTrustPolicy(),
        runner=runner,
        output_gate=gate,
    )

    output = await handler.handle(
        _activity_observation(),
        _situation_context(),
        _unauthenticated_ingress(ObservationCapability.REACT_TO_ACTIVITY),
    )

    assert output == PresentedOutput(text=None)
    assert runner.calls == 0
    assert gate.checked == 0


@pytest.mark.anyio
async def test_sendable_reaction_output_passes_through_output_safety_gate() -> None:
    """Sendable event reaction output is checked by OutputSafetyGate exactly once."""
    runner = _RecordingRunner(PresentedOutput(text="Welcome back."))
    gate = _RecordingOutputGate(GateDecision.ALLOW)
    handler = ActivityEventReactionHandler(
        trust_policy=ObservationTrustPolicy(),
        runner=runner,
        output_gate=gate,
    )

    output = await handler.handle(
        _activity_observation(),
        _situation_context(),
        _ingress(ObservationCapability.REACT_TO_ACTIVITY),
    )

    assert runner.calls == 1
    assert gate.checked == 1
    assert output.is_sendable
    assert output.text == "Welcome back."


@pytest.mark.anyio
async def test_output_safety_block_returns_no_send_output() -> None:
    """OutputSafetyGate BLOCK converts reaction output to no-send."""
    runner = _RecordingRunner(PresentedOutput(text="blocked text"))
    gate = _RecordingOutputGate(GateDecision.BLOCK)
    handler = ActivityEventReactionHandler(
        trust_policy=ObservationTrustPolicy(),
        runner=runner,
        output_gate=gate,
    )

    output = await handler.handle(
        _activity_observation(),
        _situation_context(),
        _ingress(ObservationCapability.REACT_TO_ACTIVITY),
    )

    assert runner.calls == 1
    assert gate.checked == 1
    assert output == PresentedOutput(text=None)


@pytest.mark.anyio
async def test_runner_returns_none_skips_gate() -> None:
    """When runner returns None, output gate is not called."""
    runner = _RecordingRunner(None)
    gate = _RecordingOutputGate(GateDecision.ALLOW)
    handler = ActivityEventReactionHandler(
        trust_policy=ObservationTrustPolicy(),
        runner=runner,
        output_gate=gate,
    )

    output = await handler.handle(
        _activity_observation(),
        _situation_context(),
        _ingress(ObservationCapability.REACT_TO_ACTIVITY),
    )

    assert runner.calls == 1
    assert gate.checked == 0
    assert output == PresentedOutput(text=None)


@pytest.mark.anyio
async def test_runner_returns_no_send_output_skips_gate() -> None:
    """When runner returns non-sendable output, output gate is not called."""
    runner = _RecordingRunner(PresentedOutput(text=None))
    gate = _RecordingOutputGate(GateDecision.ALLOW)
    handler = ActivityEventReactionHandler(
        trust_policy=ObservationTrustPolicy(),
        runner=runner,
        output_gate=gate,
    )

    output = await handler.handle(
        _activity_observation(),
        _situation_context(),
        _ingress(ObservationCapability.REACT_TO_ACTIVITY),
    )

    assert runner.calls == 1
    assert gate.checked == 0
    assert output == PresentedOutput(text=None)


def _activity_observation() -> ActivityEventObservation:
    return ActivityEventObservation(
        observation_id=ObservationId("obs-activity"),
        session_id=SessionId("session-1"),
        context=ObservationContext(actor=_identity(), source="test"),
        occurred_at=_OCCURRED_AT,
        kind=ObservationKind.ACTIVITY_EVENT,
        activity_kind=ActivityKind.VOICE_JOINED,
    )


def _identity() -> Identity:
    return Identity(
        actor_id=ActorId("actor-1"),
        actor_kind=ActorKind.HUMAN,
        display_name="Mina",
        provider="test",
        provider_subject=ExternalRef("user-1"),
    )


def _situation_context() -> SituationContextSnapshot:
    return SituationContextSnapshot(
        availability=AvailabilitySnapshot(
            actor_id=ActorId("actor-1"),
            status=AvailabilityStatus.AVAILABLE,
            reason="test",
            observed_at=_OCCURRED_AT,
            computed_at=_OCCURRED_AT,
            confidence=1.0,
        )
    )


def _ingress(*capabilities: ObservationCapability) -> ObservationIngressContext:
    return ObservationIngressContext(
        adapter_id="test",
        provider="test",
        authenticated=True,
        capabilities=frozenset(capabilities),
    )


def _unauthenticated_ingress(*capabilities: ObservationCapability) -> ObservationIngressContext:
    """未認証 ingress context（境界テスト用）。"""
    return ObservationIngressContext(
        adapter_id="external_client",
        provider=None,
        authenticated=False,
        capabilities=frozenset(capabilities),
    )


@dataclass
class _RecordingRunner:
    """react() 呼び出しを記録し、固定出力を返すテストダブル。"""

    output: PresentedOutput | None
    calls: int = field(default=0, init=False)

    async def react(
        self,
        observation: ActivityEventObservation,
        *,
        situation_context: SituationContextSnapshot,
    ) -> PresentedOutput | None:
        """呼び出しを記録し固定出力を返す。"""
        _ = observation, situation_context
        self.calls += 1
        return self.output


class _RecordingOutputGate:
    def __init__(self, decision: GateDecision) -> None:
        self._decision = decision
        self.checked = 0

    async def check_output(self, output: PresentedOutput) -> SafetyDecision:
        self.checked += 1
        return SafetyDecision(decision=self._decision, reason=output.text)
