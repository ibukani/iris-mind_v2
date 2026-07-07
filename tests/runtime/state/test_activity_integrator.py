"""activity integrator tests。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from iris.contracts.activity import ActivityKind, InteractionActivitySnapshot
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActivityEventObservation,
    IdleTickObservation,
    ObservationContext,
    ObservationKind,
    PresenceSignalObservation,
)
from iris.contracts.presence import PresenceStatus
from iris.core.ids import ActorId, ObservationId, SessionId, SpaceId
from iris.runtime.ingress.observation_ingress import (
    ObservationCapability,
    ObservationIngressContext,
)
from iris.runtime.ingress.observation_trust import ObservationTrustPolicy
from iris.runtime.state.activity_integrator import ActivityIntegrator
from iris.runtime.state.activity_journal import InMemoryActivityJournal
from iris.runtime.state.activity_projection import InMemoryActivityProjectionStore
from iris.runtime.state.interaction_activity import InMemoryInteractionActivityProjectionStore

_OCCURRED_AT = datetime(2026, 6, 13, tzinfo=UTC)
_RECEIVED_AT = _OCCURRED_AT + timedelta(seconds=1)


@pytest.mark.anyio
async def test_activity_integrator_records_only_with_activity_capability() -> None:
    """INTEGRATE_ACTIVITY capabilityがある場合だけactivityを統合する。"""
    journal = InMemoryActivityJournal()
    projections = InMemoryActivityProjectionStore()
    integrator = _integrator(journal, projections)
    observation = _activity_observation()

    await integrator.integrate_observation(observation, _ingress())

    event = await projections.latest_for_actor(ActorId("actor-1"))
    assert event is not None
    assert event.observation_id == observation.observation_id
    assert event.provider_event_id == "event-1"
    assert event.provider_sequence == 2
    assert event.space_id == SpaceId("space-1")
    assert event.received_at == _RECEIVED_AT


@pytest.mark.anyio
async def test_activity_integrator_rejects_source_spoof_without_capability() -> None:
    """ObservationContext.sourceだけではtrustを得られない。"""
    journal = InMemoryActivityJournal()
    projections = InMemoryActivityProjectionStore()
    integrator = _integrator(journal, projections)

    await integrator.integrate_observation(
        _activity_observation(source="discord_gateway"),
        _ingress(authenticated=False),
    )

    assert await projections.latest_for_actor(ActorId("actor-1")) is None


@pytest.mark.anyio
async def test_activity_integrator_rejects_metadata_granted_trust() -> None:
    """Observation metadataとcontext metadataはtrustを付与しない。"""
    journal = InMemoryActivityJournal()
    projections = InMemoryActivityProjectionStore()
    integrator = _integrator(journal, projections)

    await integrator.integrate_observation(
        _activity_observation(
            metadata={"capability": "integrate_activity"},
            context_metadata={"capability": "integrate_activity"},
        ),
        _ingress(capabilities=frozenset()),
    )

    assert await projections.latest_for_actor(ActorId("actor-1")) is None


@pytest.mark.anyio
async def test_activity_integrator_capability_is_isolated_from_presence() -> None:
    """Presence capabilityはactivity integrationを許可しない。"""
    journal = InMemoryActivityJournal()
    projections = InMemoryActivityProjectionStore()
    integrator = _integrator(journal, projections)

    await integrator.integrate_observation(
        _activity_observation(),
        _ingress(capabilities=frozenset({ObservationCapability.INTEGRATE_PRESENCE})),
    )

    assert await projections.latest_for_actor(ActorId("actor-1")) is None


@pytest.mark.anyio
async def test_activity_integrator_duplicate_does_not_update_projections() -> None:
    """Duplicate provider eventはlatest actor/space projectionを更新しない。"""
    journal = InMemoryActivityJournal()
    projections = InMemoryActivityProjectionStore()
    integrator = _integrator(journal, projections)
    first = _activity_observation()
    duplicate = _activity_observation(
        observation_id=ObservationId("obs-2"),
        activity_kind=ActivityKind.VOICE_LEFT,
    )

    await integrator.integrate_observation(first, _ingress())
    await integrator.integrate_observation(duplicate, _ingress())

    event = await projections.latest_for_actor(ActorId("actor-1"))
    assert event is not None
    assert event.observation_id == ObservationId("obs-1")
    assert event.kind is ActivityKind.VOICE_JOINED


@pytest.mark.anyio
async def test_activity_integrator_ignores_other_observation_kinds() -> None:
    """ActivityEventObservation以外はrecordを作らない。"""
    journal = InMemoryActivityJournal()
    projections = InMemoryActivityProjectionStore()
    integrator = _integrator(journal, projections)

    await integrator.integrate_observation(
        IdleTickObservation(
            observation_id=ObservationId("obs-idle"),
            session_id=SessionId("session-1"),
            context=ObservationContext(source="internal"),
            occurred_at=_OCCURRED_AT,
            kind=ObservationKind.IDLE_TICK,
        ),
        _ingress(),
    )
    await integrator.integrate_observation(
        PresenceSignalObservation(
            observation_id=ObservationId("obs-presence"),
            session_id=SessionId("session-1"),
            context=ObservationContext(source="internal"),
            occurred_at=_OCCURRED_AT,
            kind=ObservationKind.PRESENCE_SIGNAL,
            status=PresenceStatus.ONLINE,
        ),
        _ingress(),
    )

    assert await projections.latest_for_actor(ActorId("actor-1")) is None


@pytest.mark.anyio
async def test_activity_integrator_updates_interaction_projection_only_when_trusted() -> None:
    """認証済みINTEGRATE_ACTIVITY ingressだけがinteraction stateを更新する。"""
    interaction = InMemoryInteractionActivityProjectionStore()
    integrator = ActivityIntegrator(
        journal=InMemoryActivityJournal(),
        projections=InMemoryActivityProjectionStore(),
        trust_policy=ObservationTrustPolicy(),
        now=_now,
        interaction_projections=interaction,
        interaction_max_ttl_seconds=60,
    )
    observation = _activity_observation(
        activity_kind=ActivityKind.ACTOR_INPUT_STARTED,
        metadata={"modality": "voice", "reason": "recording"},
    )

    await integrator.integrate_observation(observation, _ingress(authenticated=False))
    assert await _active_interactions(interaction) == ()

    await integrator.integrate_observation(observation, _ingress())
    active = await _active_interactions(interaction)
    assert len(active) == 1
    assert active[0].provider == "discord"
    assert active[0].adapter_id == "trusted-adapter"


async def _active_interactions(
    store: InMemoryInteractionActivityProjectionStore,
) -> tuple[InteractionActivitySnapshot, ...]:
    return await store.active_for_target(
        provider="discord",
        actor_id=ActorId("actor-1"),
        account_id=None,
        space_id=SpaceId("space-1"),
        now=_RECEIVED_AT,
    )


def _integrator(
    journal: InMemoryActivityJournal,
    projections: InMemoryActivityProjectionStore,
) -> ActivityIntegrator:
    return ActivityIntegrator(
        journal=journal,
        projections=projections,
        trust_policy=ObservationTrustPolicy(),
        now=_now,
    )


def _activity_observation(
    *,
    observation_id: ObservationId | None = None,
    source: str = "internal",
    activity_kind: ActivityKind = ActivityKind.VOICE_JOINED,
    metadata: dict[str, str] | None = None,
    context_metadata: dict[str, str] | None = None,
) -> ActivityEventObservation:
    return ActivityEventObservation(
        observation_id=observation_id or ObservationId("obs-1"),
        session_id=SessionId("session-1"),
        context=ObservationContext(
            actor=Identity(
                actor_id=ActorId("actor-1"),
                actor_kind=ActorKind.HUMAN,
                display_name="Actor",
            ),
            space_id=SpaceId("space-1"),
            source=source,
            metadata=context_metadata or {},
        ),
        occurred_at=_OCCURRED_AT,
        kind=ObservationKind.ACTIVITY_EVENT,
        activity_kind=activity_kind,
        provider_event_id="event-1",
        provider_sequence=2,
        metadata=metadata or {},
    )


def _ingress(
    *,
    authenticated: bool = True,
    capabilities: frozenset[ObservationCapability] = frozenset(
        {ObservationCapability.INTEGRATE_ACTIVITY}
    ),
) -> ObservationIngressContext:
    return ObservationIngressContext(
        adapter_id="trusted-adapter",
        provider="discord",
        authenticated=authenticated,
        capabilities=capabilities,
    )


def _now() -> datetime:
    return _RECEIVED_AT
