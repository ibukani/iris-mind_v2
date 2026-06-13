"""Production runtime component wiring tests for context availability."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, override

import pytest

from iris.cognitive.cycle.models import ActionSelectionResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.contracts.activity import ActivityKind
from iris.contracts.availability import AvailabilityStatus
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActivityEventObservation,
    ActorMessageObservation,
    ObservationContext,
    ObservationKind,
    PresenceSignalObservation,
)
from iris.contracts.presence import PresenceStatus
from iris.core.ids import ActorId, ObservationId, SessionId, SpaceId
from iris.runtime.app import IrisApp
from iris.runtime.config import default_runtime_config
from iris.runtime.observations.ingress import (
    ObservationCapability,
    ObservationIngressContext,
    unauthenticated_external_ingress,
)
from iris.runtime.server import build_runtime_service
from iris.runtime.service import ObservationEnvelope
from iris.runtime.wiring.state import wire_runtime_state

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import WorkspaceFrame

_OCCURRED_AT = datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC)
_RECEIVED_AT = _OCCURRED_AT + timedelta(seconds=1)
_ACTOR_ID = ActorId("actor-prod")
_SPACE_ID = SpaceId("space-prod")


class _CaptureFrameStep(PipelineStep[ActionSelectionResult]):
    """A pipeline step that captures the workspace frame it receives."""

    name = "capture"

    def __init__(self) -> None:
        self.frames: list[WorkspaceFrame] = []

    @override
    async def run(self, frame: WorkspaceFrame) -> ActionSelectionResult:
        """Store the frame and return no plans.

        Returns:
            ActionSelectionResult: empty action selection result.
        """
        self.frames.append(frame)
        return ActionSelectionResult(
            step_name=self.name,
            status=StepStatus.OK,
            action_plans=(),
        )


@pytest.mark.anyio
async def test_build_runtime_service_wires_context_availability_for_text_observations() -> None:
    """Production 配線で text 観測前に統合された state が situation_context へ届く。"""
    stores = wire_runtime_state(default_runtime_config())
    capture = _CaptureFrameStep()
    service = build_runtime_service(IrisApp(steps=[capture]), stores, now=lambda: _RECEIVED_AT)

    activity_response = await service.handle_observation(
        ObservationEnvelope(
            observation=_activity_observation(ActivityKind.APP_OPENED),
            ingress=_ingress(ObservationCapability.INTEGRATE_ACTIVITY),
        )
    )
    assert not activity_response.output.is_sendable

    presence_response = await service.handle_observation(
        ObservationEnvelope(
            observation=_presence_signal(),
            ingress=_ingress(ObservationCapability.INTEGRATE_PRESENCE),
        )
    )
    assert not presence_response.output.is_sendable

    text_response = await service.handle_observation(
        ObservationEnvelope(
            observation=_text_observation(),
            ingress=unauthenticated_external_ingress(),
        )
    )
    assert not text_response.output.is_sendable
    assert len(capture.frames) == 1

    frame = capture.frames[0]
    assert frame.situation_context.latest_activity is not None
    assert frame.situation_context.presence is not None
    assert frame.situation_context.availability is not None
    assert frame.situation_context.availability.status is AvailabilityStatus.AVAILABLE


def _activity_observation(kind: ActivityKind) -> ActivityEventObservation:
    return ActivityEventObservation(
        observation_id=ObservationId(f"obs-{kind.value}"),
        session_id=SessionId("session-prod"),
        context=_context(),
        occurred_at=_OCCURRED_AT,
        kind=ObservationKind.ACTIVITY_EVENT,
        activity_kind=kind,
    )


def _presence_signal() -> PresenceSignalObservation:
    return PresenceSignalObservation(
        observation_id=ObservationId("obs-presence"),
        session_id=SessionId("session-prod"),
        context=_context(),
        occurred_at=_OCCURRED_AT,
        kind=ObservationKind.PRESENCE_SIGNAL,
        status=PresenceStatus.ONLINE,
    )


def _text_observation() -> ActorMessageObservation:
    return ActorMessageObservation(
        observation_id=ObservationId("obs-text"),
        session_id=SessionId("session-prod"),
        context=_context(),
        occurred_at=_OCCURRED_AT,
        kind=ObservationKind.ACTOR_MESSAGE,
        text="hello",
    )


def _context() -> ObservationContext:
    return ObservationContext(
        actor=Identity(
            actor_id=_ACTOR_ID,
            actor_kind=ActorKind.HUMAN,
            display_name="Mina",
        ),
        space_id=_SPACE_ID,
        source="test",
    )


def _ingress(*capabilities: ObservationCapability) -> ObservationIngressContext:
    return ObservationIngressContext(
        adapter_id="trusted-adapter",
        provider="test",
        authenticated=True,
        capabilities=frozenset(capabilities),
    )
