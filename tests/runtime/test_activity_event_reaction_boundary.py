"""ActivityEventReactionHandler boundary tests."""

from __future__ import annotations

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
from iris.runtime.wiring.event_reaction import wire_event_reaction_runner
from iris.safety.action_gate import GateDecision, SafetyDecision

_OCCURRED_AT = datetime(2026, 6, 24, 11, 0, tzinfo=UTC)


@pytest.mark.anyio
async def test_reaction_handler_does_not_react_when_trust_policy_rejects() -> None:
    """Missing REACT_TO_ACTIVITY capability never reaches sendable output."""
    handler = ActivityEventReactionHandler(
        trust_policy=ObservationTrustPolicy(),
        runner=wire_event_reaction_runner(),
        output_gate=_RecordingOutputGate(GateDecision.ALLOW),
    )

    output = await handler.handle(
        _activity_observation(),
        _situation_context(),
        _ingress(ObservationCapability.INTEGRATE_ACTIVITY),
    )

    assert output == PresentedOutput(text=None)


@pytest.mark.anyio
async def test_reaction_handler_does_not_react_without_situation_context() -> None:
    """Missing situation context prevents event reaction runner path."""
    handler = ActivityEventReactionHandler(
        trust_policy=ObservationTrustPolicy(),
        runner=wire_event_reaction_runner(),
        output_gate=_RecordingOutputGate(GateDecision.ALLOW),
    )

    output = await handler.handle(
        _activity_observation(),
        None,
        _ingress(ObservationCapability.REACT_TO_ACTIVITY),
    )

    assert output == PresentedOutput(text=None)


@pytest.mark.anyio
async def test_sendable_reaction_output_passes_through_output_safety_gate() -> None:
    """Sendable event reaction output is checked by OutputSafetyGate."""
    gate = _RecordingOutputGate(GateDecision.ALLOW)
    handler = ActivityEventReactionHandler(
        trust_policy=ObservationTrustPolicy(),
        runner=wire_event_reaction_runner(),
        output_gate=gate,
    )

    output = await handler.handle(
        _activity_observation(),
        _situation_context(),
        _ingress(ObservationCapability.REACT_TO_ACTIVITY),
    )

    assert gate.checked == 1
    assert output.is_sendable
    assert output.text == "Welcome back."


@pytest.mark.anyio
async def test_output_safety_block_returns_no_send_output() -> None:
    """OutputSafetyGate BLOCK converts reaction output to no-send."""
    handler = ActivityEventReactionHandler(
        trust_policy=ObservationTrustPolicy(),
        runner=wire_event_reaction_runner(),
        output_gate=_RecordingOutputGate(GateDecision.BLOCK),
    )

    output = await handler.handle(
        _activity_observation(),
        _situation_context(),
        _ingress(ObservationCapability.REACT_TO_ACTIVITY),
    )

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


class _RecordingOutputGate:
    def __init__(self, decision: GateDecision) -> None:
        self._decision = decision
        self.checked = 0

    async def check_output(self, output: PresentedOutput) -> SafetyDecision:
        self.checked += 1
        return SafetyDecision(decision=self._decision, reason=output.text)
