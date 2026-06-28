"""IrisRuntimeService situation context assembly tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, override

import pytest

from iris.cognitive.cycle.models import ActionSelectionResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.contracts.activity import ActivityEventRecord, ActivityKind
from iris.contracts.availability import AvailabilityStatus
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActorMessageObservation,
    ObservationContext,
    ObservationKind,
)
from iris.contracts.presence import PresenceSnapshot, PresenceStatus
from iris.contracts.space_occupancy import SpaceOccupant
from iris.contracts.workspace_context import SituationContextSnapshot
from iris.core.ids import (
    AccountId,
    ActivityId,
    ActorId,
    DeviceId,
    ExternalRef,
    ObservationId,
    SessionId,
    SpaceId,
)

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import WorkspaceFrame
from iris.runtime.app import IrisApp
from iris.runtime.ingress.observation_ingress import unauthenticated_external_ingress
from iris.runtime.service import IrisRuntimeService, ObservationEnvelope
from iris.runtime.state.activity_projection import InMemoryActivityProjectionStore
from iris.runtime.state.availability import AvailabilityResolver
from iris.runtime.state.context_assembler import WorkspaceContextAssembler
from iris.runtime.state.presence import InMemoryPresenceStore
from iris.runtime.state.space_occupancy import InMemorySpaceOccupancyStore

_OCCURRED_AT = datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC)
_NOW = _OCCURRED_AT + timedelta(seconds=5)


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
async def test_runtime_service_passes_assembled_situation_context_to_app() -> None:
    """Service は workspace assembler で組み立てた situation_context を app に渡す。"""
    projections = InMemoryActivityProjectionStore()
    presence_store = InMemoryPresenceStore()
    occupancy_store = InMemorySpaceOccupancyStore()

    await projections.update_latest(
        ActivityEventRecord(
            activity_id=ActivityId("activity-svc"),
            observation_id=ObservationId("obs-activity"),
            provider_event_id=None,
            provider_sequence=None,
            actor_id=ActorId("actor-svc"),
            account_id=None,
            device_id=None,
            space_id=SpaceId("space-svc"),
            source=None,
            kind=ActivityKind.APP_OPENED,
            occurred_at=_OCCURRED_AT,
            received_at=_NOW,
        )
    )
    await presence_store.update_presence(
        PresenceSnapshot(
            actor_id=ActorId("actor-svc"),
            account_id=None,
            device_id=None,
            source=None,
            status=PresenceStatus.ONLINE,
            observed_at=_OCCURRED_AT,
            received_at=_NOW,
        )
    )
    await occupancy_store.actor_joined(
        space_id=SpaceId("space-svc"),
        occupant=SpaceOccupant(
            actor_id=ActorId("actor-svc"),
            joined_at=_OCCURRED_AT,
            last_seen_at=_NOW,
            expires_at=None,
        ),
    )

    capture = _CaptureFrameStep()
    app = IrisApp(steps=[capture])
    assembler = WorkspaceContextAssembler(
        activity_projection_store=projections,
        presence_store=presence_store,
        occupancy_store=occupancy_store,
        availability_resolver=AvailabilityResolver(recent_activity_window_seconds=60.0),
        now=lambda: _NOW,
    )
    service = IrisRuntimeService(app, workspace_context_assembler=assembler)

    observation = ActorMessageObservation(
        observation_id=ObservationId("obs-svc"),
        session_id=SessionId("session-svc"),
        context=ObservationContext(
            actor=Identity(
                actor_id=ActorId("actor-svc"),
                actor_kind=ActorKind.HUMAN,
                display_name="Mina",
                provider="test",
                provider_subject=ExternalRef("mina"),
            ),
            account_id=AccountId("account-svc"),
            device_id=DeviceId("device-svc"),
            space_id=SpaceId("space-svc"),
        ),
        occurred_at=_OCCURRED_AT,
        kind=ObservationKind.ACTOR_MESSAGE,
        text="hello",
    )

    response = await service.handle_observation(
        ObservationEnvelope(
            observation=observation,
            ingress=unauthenticated_external_ingress(),
        )
    )

    assert not response.output.is_sendable
    assert len(capture.frames) == 1
    frame = capture.frames[0]
    assert frame.situation_context.latest_activity is not None
    assert frame.situation_context.presence is not None
    assert frame.situation_context.space_occupancy is not None
    assert frame.situation_context.availability is not None
    assert frame.situation_context.availability.status is AvailabilityStatus.AVAILABLE


@pytest.mark.anyio
async def test_runtime_service_without_assembler_does_not_pass_context() -> None:
    """Assembler が未設定なら app に situation_context は渡されない。"""
    capture = _CaptureFrameStep()
    app = IrisApp(steps=[capture])
    service = IrisRuntimeService(app)

    observation = ActorMessageObservation(
        observation_id=ObservationId("obs-no-asm"),
        session_id=SessionId("session-no-asm"),
        context=ObservationContext(
            actor=Identity(
                actor_id=ActorId("actor-no-asm"),
                actor_kind=ActorKind.HUMAN,
                display_name="Mina",
                provider="test",
                provider_subject=ExternalRef("mina"),
            ),
            account_id=AccountId("account-no-asm"),
            device_id=DeviceId("device-no-asm"),
            space_id=None,
        ),
        occurred_at=_OCCURRED_AT,
        kind=ObservationKind.ACTOR_MESSAGE,
        text="hello",
    )

    response = await service.handle_observation(
        ObservationEnvelope(
            observation=observation,
            ingress=unauthenticated_external_ingress(),
        )
    )

    assert not response.output.is_sendable
    assert len(capture.frames) == 1
    assert capture.frames[0].situation_context == SituationContextSnapshot()
