"""presence integrator tests。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from iris.contracts.activity import ActivityKind
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActivityEventObservation,
    ObservationContext,
    ObservationKind,
    PresenceSignalObservation,
)
from iris.contracts.presence import PresenceStatus
from iris.core.ids import ActorId, ObservationId, SessionId
from iris.runtime.ingress.observation_ingress import (
    ObservationCapability,
    ObservationIngressContext,
)
from iris.runtime.ingress.observation_trust import ObservationTrustPolicy
from iris.runtime.state.presence import InMemoryPresenceStore
from iris.runtime.state.presence_integrator import PresenceIntegrator

_OCCURRED_AT = datetime(2026, 6, 13, tzinfo=UTC)
_RECEIVED_AT = _OCCURRED_AT + timedelta(seconds=1)


@pytest.mark.anyio
async def test_presence_integrator_records_only_with_presence_capability() -> None:
    """INTEGRATE_PRESENCE capabilityがある場合だけpresenceを統合する。"""
    store = InMemoryPresenceStore()
    integrator = _integrator(store)
    expires_at = _OCCURRED_AT + timedelta(minutes=5)

    await integrator.integrate_observation(
        _presence_signal(expires_at=expires_at),
        _ingress(),
    )

    snapshot = await store.get_presence_for_actor(
        ActorId("actor-1"),
        now=_OCCURRED_AT,
    )
    assert snapshot is not None
    assert snapshot.status is PresenceStatus.ONLINE
    assert snapshot.observed_at == _OCCURRED_AT
    assert snapshot.received_at == _RECEIVED_AT
    assert snapshot.expires_at == expires_at


@pytest.mark.anyio
async def test_presence_integrator_rejects_source_spoof_without_capability() -> None:
    """ObservationContext.sourceだけではpresence trustを得られない。"""
    store = InMemoryPresenceStore()
    integrator = _integrator(store)

    await integrator.integrate_observation(
        _presence_signal(source="discord_gateway"),
        _ingress(authenticated=False),
    )

    assert await store.get_presence_for_actor(ActorId("actor-1"), now=_OCCURRED_AT) is None


@pytest.mark.anyio
async def test_presence_integrator_rejects_activity_capability_and_metadata() -> None:
    """Activity capabilityやmetadataはpresence trustを付与しない。"""
    store = InMemoryPresenceStore()
    integrator = _integrator(store)

    await integrator.integrate_observation(
        _presence_signal(
            metadata={"capability": "integrate_presence"},
            context_metadata={"capability": "integrate_presence"},
        ),
        _ingress(capabilities=frozenset({ObservationCapability.INTEGRATE_ACTIVITY})),
    )

    assert await store.get_presence_for_actor(ActorId("actor-1"), now=_OCCURRED_AT) is None


@pytest.mark.anyio
async def test_presence_integrator_rejects_actorless_signal() -> None:
    """Resolved actorなしのsignalを保存しない。"""
    store = InMemoryPresenceStore()
    integrator = _integrator(store)

    await integrator.integrate_observation(
        _presence_signal(include_actor=False),
        _ingress(),
    )

    assert await store.get_presence_for_actor(ActorId("actor-1"), now=_OCCURRED_AT) is None


@pytest.mark.anyio
async def test_presence_integrator_ignores_activity_event() -> None:
    """Activity eventがPresenceStoreを更新しないことを確認する。"""
    store = InMemoryPresenceStore()
    integrator = _integrator(store)
    await integrator.integrate_observation(
        ActivityEventObservation(
            observation_id=ObservationId("obs-activity"),
            session_id=SessionId("session-1"),
            context=ObservationContext(source="internal"),
            occurred_at=_OCCURRED_AT,
            kind=ObservationKind.ACTIVITY_EVENT,
            activity_kind=ActivityKind.SYSTEM_INTERACTION,
        ),
        _ingress(),
    )

    assert await store.get_presence_for_actor(ActorId("actor-1"), now=_OCCURRED_AT) is None


def _integrator(store: InMemoryPresenceStore) -> PresenceIntegrator:
    return PresenceIntegrator(
        store=store,
        trust_policy=ObservationTrustPolicy(),
        now=_now,
    )


def _presence_signal(
    *,
    source: str = "internal",
    include_actor: bool = True,
    expires_at: datetime | None = None,
    metadata: dict[str, str] | None = None,
    context_metadata: dict[str, str] | None = None,
) -> PresenceSignalObservation:
    actor = (
        Identity(
            actor_id=ActorId("actor-1"),
            actor_kind=ActorKind.HUMAN,
            display_name="Actor",
        )
        if include_actor
        else None
    )
    return PresenceSignalObservation(
        observation_id=ObservationId("obs-presence"),
        session_id=SessionId("session-1"),
        context=ObservationContext(
            actor=actor,
            source=source,
            metadata=context_metadata or {},
        ),
        occurred_at=_OCCURRED_AT,
        kind=ObservationKind.PRESENCE_SIGNAL,
        status=PresenceStatus.ONLINE,
        expires_at=expires_at,
        metadata=metadata or {},
    )


def _ingress(
    *,
    authenticated: bool = True,
    capabilities: frozenset[ObservationCapability] = frozenset(
        {ObservationCapability.INTEGRATE_PRESENCE}
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
