"""WorkspaceFrame situation context tests."""

from __future__ import annotations

from datetime import UTC, datetime

from iris.cognitive.workspace.frame import WorkspaceFrame
from iris.contracts.activity import ActivityEventRecord, ActivityKind
from iris.contracts.availability import AvailabilitySnapshot, AvailabilityStatus
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActorMessageObservation,
    ObservationContext,
    ObservationKind,
)
from iris.contracts.presence import PresenceSnapshot, PresenceStatus
from iris.contracts.space_occupancy import SpaceOccupancySnapshot
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


def _observation() -> ActorMessageObservation:
    """Build a simple observation for workspace frame tests.

    Returns:
        ActorMessageObservation: A test observation.
    """
    return ActorMessageObservation(
        observation_id=ObservationId("obs-situation"),
        session_id=SessionId("session-situation"),
        context=ObservationContext(
            actor=Identity(
                actor_id=ActorId("actor-situation"),
                actor_kind=ActorKind.HUMAN,
                display_name="Mina",
                provider="test",
                provider_subject=ExternalRef("mina"),
            ),
            account_id=AccountId("account-situation"),
            device_id=DeviceId("device-situation"),
            space_id=SpaceId("space-situation"),
        ),
        occurred_at=datetime(2026, 6, 13, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text="hello",
    )


def test_workspace_frame_has_empty_situation_context_by_default() -> None:
    """WorkspaceFrame はデフォルトで空の SituationContextSnapshot を持つ。"""
    frame = WorkspaceFrame(observation=_observation())
    assert frame.situation_context == SituationContextSnapshot()


def test_situation_context_can_hold_latest_activity() -> None:
    """SituationContextSnapshot に latest_activity を設定できる。"""
    activity = ActivityEventRecord(
        activity_id=ActivityId("activity-1"),
        observation_id=ObservationId("obs-1"),
        provider_event_id=None,
        provider_sequence=None,
        actor_id=ActorId("actor-1"),
        account_id=None,
        device_id=None,
        space_id=None,
        source=None,
        kind=ActivityKind.APP_OPENED,
        occurred_at=datetime(2026, 6, 13, tzinfo=UTC),
        received_at=datetime(2026, 6, 13, tzinfo=UTC),
    )
    context = SituationContextSnapshot(latest_activity=activity)
    assert context.latest_activity is activity


def test_situation_context_can_hold_presence() -> None:
    """SituationContextSnapshot に presence を設定できる。"""
    presence = PresenceSnapshot(
        actor_id=ActorId("actor-1"),
        account_id=None,
        device_id=None,
        source=None,
        status=PresenceStatus.ONLINE,
        observed_at=datetime(2026, 6, 13, tzinfo=UTC),
        received_at=datetime(2026, 6, 13, tzinfo=UTC),
    )
    context = SituationContextSnapshot(presence=presence)
    assert context.presence is presence


def test_situation_context_can_hold_space_occupancy() -> None:
    """SituationContextSnapshot に space_occupancy を設定できる。"""
    occupancy = SpaceOccupancySnapshot(
        space_id=SpaceId("space-1"),
        occupants=(),
        updated_at=datetime(2026, 6, 13, tzinfo=UTC),
    )
    context = SituationContextSnapshot(space_occupancy=occupancy)
    assert context.space_occupancy is occupancy


def test_situation_context_can_hold_availability() -> None:
    """SituationContextSnapshot に availability を設定できる。"""
    availability = AvailabilitySnapshot(
        actor_id=ActorId("actor-1"),
        status=AvailabilityStatus.AVAILABLE,
        reason="online with recent activity",
        observed_at=datetime(2026, 6, 13, tzinfo=UTC),
        computed_at=datetime(2026, 6, 13, tzinfo=UTC),
        confidence=0.9,
    )
    context = SituationContextSnapshot(availability=availability)
    assert context.availability is availability
