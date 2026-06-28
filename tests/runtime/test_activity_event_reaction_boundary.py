"""ActivityEventReactionHandler boundary tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from iris.contracts.actions import ActionPlan, PresentedOutput
from iris.contracts.activity import ActivityKind
from iris.contracts.availability import AvailabilitySnapshot, AvailabilityStatus
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActivityEventObservation,
    ObservationContext,
    ObservationKind,
)
from iris.contracts.workspace_context import SituationContextSnapshot
from iris.core.ids import ActorId, ExternalRef, ObservationId, SessionId
from iris.runtime.ingress.activity_event_reaction import ActivityEventReactionHandler
from iris.runtime.ingress.observation_ingress import (
    ObservationCapability,
    ObservationIngressContext,
)
from iris.runtime.ingress.observation_trust import ObservationTrustPolicy

_OCCURRED_AT = datetime(2026, 6, 24, 11, 0, tzinfo=UTC)


def _candidate(text: str = "test") -> ActionPlan:
    return ActionPlan(
        turn_intent="event_reaction",
        candidate_text=text,
        should_respond=True,
        priority=1,
    )


@pytest.mark.anyio
async def test_reaction_handler_does_not_react_when_trust_policy_rejects() -> None:
    """Missing REACT_TO_ACTIVITY capability never calls runner or output gate."""
    runner = _RecordingDecisionPipeline(_candidate())
    pipeline = _RecordingOutputPipeline(PresentedOutput(text="should not appear"))
    handler = ActivityEventReactionHandler(
        trust_policy=ObservationTrustPolicy(),
        decision_pipeline=runner,
        output_pipeline=pipeline,
    )

    output = await handler.handle(
        _activity_observation(),
        _situation_context(),
        _ingress(ObservationCapability.INTEGRATE_ACTIVITY),
    )

    assert output == PresentedOutput(text=None)
    assert runner.calls == 0
    assert pipeline.calls == 0


@pytest.mark.anyio
async def test_reaction_handler_does_not_react_without_situation_context() -> None:
    """Missing situation context prevents runner and output gate calls."""
    runner = _RecordingDecisionPipeline(_candidate())
    pipeline = _RecordingOutputPipeline(PresentedOutput(text="should not appear"))
    handler = ActivityEventReactionHandler(
        trust_policy=ObservationTrustPolicy(),
        decision_pipeline=runner,
        output_pipeline=pipeline,
    )

    output = await handler.handle(
        _activity_observation(),
        None,
        _ingress(ObservationCapability.REACT_TO_ACTIVITY),
    )

    assert output == PresentedOutput(text=None)
    assert runner.calls == 0
    assert pipeline.calls == 0


@pytest.mark.anyio
async def test_unauthenticated_ingress_blocks_reaction_even_with_capability() -> None:
    """Unauthenticated ingress with REACT_TO_ACTIVITY capability is still blocked."""
    runner = _RecordingDecisionPipeline(_candidate())
    pipeline = _RecordingOutputPipeline(PresentedOutput(text="should not appear"))
    handler = ActivityEventReactionHandler(
        trust_policy=ObservationTrustPolicy(),
        decision_pipeline=runner,
        output_pipeline=pipeline,
    )

    output = await handler.handle(
        _activity_observation(),
        _situation_context(),
        _unauthenticated_ingress(ObservationCapability.REACT_TO_ACTIVITY),
    )

    assert output == PresentedOutput(text=None)
    assert runner.calls == 0
    assert pipeline.calls == 0


@pytest.mark.anyio
async def test_sendable_reaction_output_passes_through_output_safety_gate() -> None:
    """Sendable event reaction output is checked by OutputSafetyGate exactly once."""
    runner = _RecordingDecisionPipeline(_candidate("Welcome back."))
    pipeline = _RecordingOutputPipeline(PresentedOutput(text="Welcome back."))
    handler = ActivityEventReactionHandler(
        trust_policy=ObservationTrustPolicy(),
        decision_pipeline=runner,
        output_pipeline=pipeline,
    )

    output = await handler.handle(
        _activity_observation(),
        _situation_context(),
        _ingress(ObservationCapability.REACT_TO_ACTIVITY),
    )

    assert runner.calls == 1
    assert pipeline.calls == 1
    assert output.is_sendable
    assert output.text == "Welcome back."


@pytest.mark.anyio
async def test_output_safety_block_returns_no_send_output() -> None:
    """OutputSafetyGate BLOCK converts reaction output to no-send."""
    runner = _RecordingDecisionPipeline(_candidate("blocked"))
    pipeline = _RecordingOutputPipeline(PresentedOutput(text=None))
    handler = ActivityEventReactionHandler(
        trust_policy=ObservationTrustPolicy(),
        decision_pipeline=runner,
        output_pipeline=pipeline,
    )

    output = await handler.handle(
        _activity_observation(),
        _situation_context(),
        _ingress(ObservationCapability.REACT_TO_ACTIVITY),
    )

    assert runner.calls == 1
    assert pipeline.calls == 1
    assert output == PresentedOutput(text=None)


@pytest.mark.anyio
async def test_runner_returns_none_skips_gate() -> None:
    """When runner returns None, output gate is not called."""
    runner = _RecordingDecisionPipeline(None)
    pipeline = _RecordingOutputPipeline(PresentedOutput(text="should not appear"))
    handler = ActivityEventReactionHandler(
        trust_policy=ObservationTrustPolicy(),
        decision_pipeline=runner,
        output_pipeline=pipeline,
    )

    output = await handler.handle(
        _activity_observation(),
        _situation_context(),
        _ingress(ObservationCapability.REACT_TO_ACTIVITY),
    )

    assert runner.calls == 1
    assert pipeline.calls == 0
    assert output == PresentedOutput(text=None)


@pytest.mark.anyio
async def test_runner_returns_no_send_output_skips_gate() -> None:
    """When runner returns non-sendable output, output gate is not called."""
    runner = _RecordingDecisionPipeline(_candidate(""))
    pipeline = _RecordingOutputPipeline(PresentedOutput(text=None))
    handler = ActivityEventReactionHandler(
        trust_policy=ObservationTrustPolicy(),
        decision_pipeline=runner,
        output_pipeline=pipeline,
    )

    output = await handler.handle(
        _activity_observation(),
        _situation_context(),
        _ingress(ObservationCapability.REACT_TO_ACTIVITY),
    )

    assert runner.calls == 1
    assert pipeline.calls == 1
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
    return ObservationIngressContext(
        adapter_id="external_client",
        provider=None,
        authenticated=False,
        capabilities=frozenset(capabilities),
    )


@dataclass
class _RecordingDecisionPipeline:
    candidate: ActionPlan | None
    calls: int = field(default=0, init=False)

    async def decide(
        self,
        observation: ActivityEventObservation,
        *,
        situation_context: SituationContextSnapshot,
    ) -> ActionPlan | None:
        del observation, situation_context
        self.calls += 1
        return self.candidate


@dataclass
class _RecordingOutputPipeline:
    output: PresentedOutput
    calls: int = field(default=0, init=False)

    async def present_action_plan(
        self,
        plan: ActionPlan,
    ) -> PresentedOutput:
        del plan
        self.calls += 1
        return self.output
