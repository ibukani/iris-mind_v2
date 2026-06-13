"""WorkspaceContextAssembler tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

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
from iris.runtime.activity.projections import InMemoryActivityProjectionStore
from iris.runtime.availability.resolver import AvailabilityResolver
from iris.runtime.context.workspace_assembler import WorkspaceContextAssembler
from iris.runtime.presence.store import InMemoryPresenceStore
from iris.runtime.spaces.occupancy_store import InMemorySpaceOccupancyStore

_OCCURRED_AT = datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC)
_NOW = _OCCURRED_AT + timedelta(seconds=5)


def _actor_identity() -> Identity:
    return Identity(
        actor_id=ActorId("actor-assembler"),
        actor_kind=ActorKind.HUMAN,
        display_name="Mina",
        provider="test",
        provider_subject=ExternalRef("mina"),
    )


def _observation() -> ActorMessageObservation:
    return ActorMessageObservation(
        observation_id=ObservationId("obs-assembler"),
        session_id=SessionId("session-assembler"),
        context=ObservationContext(
            actor=_actor_identity(),
            account_id=AccountId("account-assembler"),
            device_id=DeviceId("device-assembler"),
            space_id=SpaceId("space-assembler"),
        ),
        occurred_at=_OCCURRED_AT,
        kind=ObservationKind.ACTOR_MESSAGE,
        text="hello",
    )


@pytest.mark.anyio
async def test_assemble_collects_activity_presence_and_occupancy() -> None:
    """Assembler は各 store から actor / space の状態を収集する。"""
    projections = InMemoryActivityProjectionStore()
    presence_store = InMemoryPresenceStore()
    occupancy_store = InMemorySpaceOccupancyStore()

    activity = ActivityEventRecord(
        activity_id=ActivityId("activity-assembler"),
        observation_id=ObservationId("obs-activity"),
        provider_event_id=None,
        provider_sequence=None,
        actor_id=ActorId("actor-assembler"),
        account_id=None,
        device_id=None,
        space_id=SpaceId("space-assembler"),
        source=None,
        kind=ActivityKind.APP_OPENED,
        occurred_at=_OCCURRED_AT,
        received_at=_NOW,
    )
    await projections.update_latest(activity)

    presence = PresenceSnapshot(
        actor_id=ActorId("actor-assembler"),
        account_id=None,
        device_id=None,
        source=None,
        status=PresenceStatus.ONLINE,
        observed_at=_OCCURRED_AT,
        received_at=_NOW,
    )
    await presence_store.update_presence(presence)

    await occupancy_store.actor_joined(
        space_id=SpaceId("space-assembler"),
        occupant=SpaceOccupant(
            actor_id=ActorId("actor-assembler"),
            account_id=None,
            device_id=None,
            joined_at=_OCCURRED_AT,
            last_seen_at=_NOW,
            expires_at=None,
        ),
    )

    assembler = WorkspaceContextAssembler(
        activity_projection_store=projections,
        presence_store=presence_store,
        occupancy_store=occupancy_store,
        availability_resolver=AvailabilityResolver(recent_activity_window_seconds=60.0),
        now=lambda: _NOW,
    )

    context = await assembler.assemble(_observation())

    assert context.latest_activity is activity
    assert context.presence is presence
    assert context.space_occupancy is not None
    assert context.space_occupancy.space_id == SpaceId("space-assembler")
    assert context.availability is not None
    assert context.availability.status is AvailabilityStatus.AVAILABLE


@pytest.mark.anyio
async def test_assemble_with_no_stores_returns_empty_context() -> None:
    """Store が全て無ければ空の context を返す。"""
    assembler = WorkspaceContextAssembler(
        activity_projection_store=None,
        presence_store=None,
        occupancy_store=None,
        availability_resolver=AvailabilityResolver(),
        now=lambda: _NOW,
    )

    context = await assembler.assemble(_observation())

    assert context.latest_activity is None
    assert context.presence is None
    assert context.space_occupancy is None
    assert context.availability is not None
    assert context.availability.status is AvailabilityStatus.UNKNOWN


@pytest.mark.anyio
async def test_assemble_returns_none_for_unknown_actor_or_space() -> None:
    """actor_id / space_id が無い observation では store 問い合わせを行わない。"""
    projections = InMemoryActivityProjectionStore()
    presence_store = InMemoryPresenceStore()
    occupancy_store = InMemorySpaceOccupancyStore()

    assembler = WorkspaceContextAssembler(
        activity_projection_store=projections,
        presence_store=presence_store,
        occupancy_store=occupancy_store,
        availability_resolver=AvailabilityResolver(),
        now=lambda: _NOW,
    )

    observation = ActorMessageObservation(
        observation_id=ObservationId("obs-empty"),
        session_id=SessionId("session-empty"),
        context=ObservationContext(
            actor=None,
            account_id=None,
            device_id=None,
            space_id=None,
        ),
        occurred_at=_OCCURRED_AT,
        kind=ObservationKind.ACTOR_MESSAGE,
        text="hello",
    )
    context = await assembler.assemble(observation)

    assert context.latest_activity is None
    assert context.presence is None
    assert context.space_occupancy is None
    assert context.availability is not None
    assert context.availability.status is AvailabilityStatus.UNKNOWN
