"""space occupancy integrator tests。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from iris.contracts.activity import ActivityKind
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActivityEventObservation,
    ObservationContext,
    ObservationKind,
)
from iris.core.ids import ActorId, ObservationId, SessionId, SpaceId
from iris.runtime.ingress.observation_ingress import (
    ObservationCapability,
    ObservationIngressContext,
)
from iris.runtime.ingress.observation_trust import ObservationTrustPolicy
from iris.runtime.state.space_occupancy import InMemorySpaceOccupancyStore
from iris.runtime.state.space_occupancy_integrator import SpaceOccupancyIntegrator

_OCCURRED_AT = datetime(2026, 6, 13, tzinfo=UTC)
_RECEIVED_AT = _OCCURRED_AT + timedelta(seconds=1)
_SPACE_ID = SpaceId("space-1")


@pytest.mark.anyio
async def test_voice_join_and_leave_update_occupancy_with_capability() -> None:
    """UPDATE_SPACE_OCCUPANCY capabilityがある場合だけoccupancyを更新する。"""
    store = InMemorySpaceOccupancyStore()
    integrator = _integrator(store)

    await integrator.integrate_observation(
        _activity(ActivityKind.VOICE_JOINED),
        _ingress(),
    )

    joined = await store.get_occupancy(_SPACE_ID, now=_RECEIVED_AT)
    assert tuple(occupant.actor_id for occupant in joined.occupants) == (ActorId("actor-1"),)
    assert joined.occupants[0].joined_at == _OCCURRED_AT
    assert joined.occupants[0].last_seen_at == _RECEIVED_AT

    await integrator.integrate_observation(
        _activity(ActivityKind.VOICE_LEFT),
        _ingress(),
    )

    left = await store.get_occupancy(_SPACE_ID, now=_RECEIVED_AT)
    assert left.occupants == ()


@pytest.mark.anyio
async def test_occupancy_integrator_rejects_activity_capability_only() -> None:
    """INTEGRATE_ACTIVITYだけではoccupancyを更新できない。"""
    store = InMemorySpaceOccupancyStore()
    integrator = _integrator(store)

    await integrator.integrate_observation(
        _activity(ActivityKind.VOICE_JOINED, source="discord_gateway"),
        _ingress(capabilities=frozenset({ObservationCapability.INTEGRATE_ACTIVITY})),
    )

    snapshot = await store.get_occupancy(_SPACE_ID, now=_RECEIVED_AT)
    assert snapshot.occupants == ()


@pytest.mark.anyio
async def test_occupancy_integrator_ignores_non_voice_or_incomplete_event() -> None:
    """Voice kind、resolved actor/space条件を満たさないeventを無視する。"""
    store = InMemorySpaceOccupancyStore()
    integrator = _integrator(store)

    await integrator.integrate_observation(_activity(ActivityKind.APP_OPENED), _ingress())
    await integrator.integrate_observation(
        _activity(ActivityKind.VOICE_JOINED, include_actor=False),
        _ingress(),
    )
    await integrator.integrate_observation(
        _activity(ActivityKind.VOICE_JOINED, include_space=False),
        _ingress(),
    )

    snapshot = await store.get_occupancy(_SPACE_ID, now=_RECEIVED_AT)
    assert snapshot.occupants == ()


def _integrator(store: InMemorySpaceOccupancyStore) -> SpaceOccupancyIntegrator:
    return SpaceOccupancyIntegrator(
        store=store,
        trust_policy=ObservationTrustPolicy(),
        now=_now,
    )


def _activity(
    kind: ActivityKind,
    *,
    source: str = "internal",
    include_actor: bool = True,
    include_space: bool = True,
) -> ActivityEventObservation:
    actor = (
        Identity(
            actor_id=ActorId("actor-1"),
            actor_kind=ActorKind.HUMAN,
            display_name="Actor",
        )
        if include_actor
        else None
    )
    return ActivityEventObservation(
        observation_id=ObservationId(f"obs-{kind.value}"),
        session_id=SessionId("session-1"),
        context=ObservationContext(
            actor=actor,
            space_id=_SPACE_ID if include_space else None,
            source=source,
        ),
        occurred_at=_OCCURRED_AT,
        kind=ObservationKind.ACTIVITY_EVENT,
        activity_kind=kind,
    )


def _ingress(
    *,
    capabilities: frozenset[ObservationCapability] = frozenset(
        {ObservationCapability.UPDATE_SPACE_OCCUPANCY}
    ),
) -> ObservationIngressContext:
    return ObservationIngressContext(
        adapter_id="trusted-adapter",
        provider="discord",
        authenticated=True,
        capabilities=capabilities,
    )


def _now() -> datetime:
    return _RECEIVED_AT
