"""activity integrator tests。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from iris.contracts.activity import ActivityKind
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActivityEventObservation,
    IdleTickObservation,
    ObservationContext,
    ObservationKind,
    PresenceSignalObservation,
)
from iris.contracts.presence import PresenceStatus
from iris.core.ids import ActivityId, ActorId, ObservationId, SessionId, SpaceId
from iris.runtime.activity.integrator import ActivityIntegrator
from iris.runtime.activity.store import InMemoryActivityStore
from iris.runtime.observations.trust import ObservationTrustPolicy

_OCCURRED_AT = datetime(2026, 6, 13, tzinfo=UTC)
_RECEIVED_AT = _OCCURRED_AT + timedelta(seconds=1)


@pytest.mark.anyio
async def test_activity_integrator_records_trusted_event() -> None:
    """Trusted activity claimが内部recordへ変換されることを確認する。"""
    store = InMemoryActivityStore()
    integrator = _integrator(store)
    observation = _activity_observation()

    await integrator.integrate_observation(observation)

    record = await store.latest_for_actor(ActorId("actor-1"))
    assert record is not None
    assert record.observation_id == observation.observation_id
    assert record.provider_event_id == "event-1"
    assert record.provider_sequence == 2
    assert record.space_id == SpaceId("space-1")
    assert record.received_at == _RECEIVED_AT


@pytest.mark.anyio
async def test_activity_integrator_rejects_untrusted_and_ignores_other_kinds() -> None:
    """Untrusted activityと他のobservation kindがrecordを作らないことを確認する。"""
    store = InMemoryActivityStore()
    integrator = _integrator(store)

    await integrator.integrate_observation(_activity_observation(source="untrusted"))
    await integrator.integrate_observation(
        IdleTickObservation(
            observation_id=ObservationId("obs-idle"),
            session_id=SessionId("session-1"),
            context=ObservationContext(source="internal"),
            occurred_at=_OCCURRED_AT,
            kind=ObservationKind.IDLE_TICK,
        )
    )
    await integrator.integrate_observation(
        PresenceSignalObservation(
            observation_id=ObservationId("obs-presence"),
            session_id=SessionId("session-1"),
            context=ObservationContext(source="internal"),
            occurred_at=_OCCURRED_AT,
            kind=ObservationKind.PRESENCE_SIGNAL,
            status=PresenceStatus.ONLINE,
        )
    )

    assert await store.latest_for_actor(ActorId("actor-1")) is None


@pytest.mark.anyio
async def test_activity_integrator_provider_event_is_idempotent() -> None:
    """同じprovider event claimが一度だけ統合されることを確認する。"""
    store = InMemoryActivityStore()
    integrator = _integrator(store)
    first = _activity_observation()
    duplicate = ActivityEventObservation(
        observation_id=ObservationId("obs-2"),
        session_id=first.session_id,
        context=first.context,
        occurred_at=first.occurred_at,
        kind=first.kind,
        activity_kind=first.activity_kind,
        provider_event_id=first.provider_event_id,
        provider_sequence=first.provider_sequence,
    )

    await integrator.integrate_observation(first)
    await integrator.integrate_observation(duplicate)

    first_activity_id = _activity_id(first)
    assert await store.get_by_id(first_activity_id) is not None
    assert await store.get_by_id(_activity_id(duplicate)) is None
    assert str(first_activity_id) == "activity:obs-1"


def _integrator(store: InMemoryActivityStore) -> ActivityIntegrator:
    policy = ObservationTrustPolicy(
        trusted_activity_sources=frozenset({"internal"}),
        trusted_presence_sources=frozenset(),
    )
    return ActivityIntegrator(store=store, trust_policy=policy, now=_now)


def _activity_observation(
    *,
    source: str = "internal",
) -> ActivityEventObservation:
    return ActivityEventObservation(
        observation_id=ObservationId("obs-1"),
        session_id=SessionId("session-1"),
        context=ObservationContext(
            actor=Identity(
                actor_id=ActorId("actor-1"),
                actor_kind=ActorKind.HUMAN,
                display_name="Actor",
            ),
            space_id=SpaceId("space-1"),
            source=source,
        ),
        occurred_at=_OCCURRED_AT,
        kind=ObservationKind.ACTIVITY_EVENT,
        activity_kind=ActivityKind.VOICE_JOINED,
        provider_event_id="event-1",
        provider_sequence=2,
    )


def _activity_id(observation: ActivityEventObservation) -> ActivityId:
    return ActivityId(f"activity:{observation.observation_id}")


def _now() -> datetime:
    return _RECEIVED_AT
