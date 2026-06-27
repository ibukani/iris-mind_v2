"""Scheduler target integrator tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.contracts.delivery import DeliveryRouteHint
from iris.contracts.observations import ActorMessageObservation, ObservationContext, ObservationKind
from iris.core.ids import ExternalRef, ObservationId, SessionId
from iris.runtime.ingress.observation_ingress import (
    ObservationCapability,
    ObservationIngressContext,
)
from iris.runtime.state.scheduler_target_integrator import SchedulerTargetIntegrator
from iris.runtime.state.scheduler_targets import InMemorySchedulerTargetStore

pytestmark = pytest.mark.anyio


def _observation() -> ActorMessageObservation:
    return ActorMessageObservation(
        observation_id=ObservationId("obs-1"),
        session_id=SessionId("session-1"),
        context=ObservationContext(source="grpc"),
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text="hello",
        external_message_id=None,
    )


async def test_target_integrator_updates_from_trusted_route_hint() -> None:
    """Trusted ingress with capability and route hint registers a target."""
    store = InMemorySchedulerTargetStore()
    integrator = SchedulerTargetIntegrator(store)
    await integrator.integrate_observation(
        _observation(),
        ObservationIngressContext(
            adapter_id="grpc",
            provider="grpc",
            authenticated=True,
            capabilities=frozenset({ObservationCapability.REGISTER_DELIVERY_TARGET}),
            delivery_route=DeliveryRouteHint(
                provider="discord",
                provider_subject=ExternalRef("user-1"),
                provider_space_ref=None,
            ),
        ),
    )
    targets = await store.list_targets(now=datetime(2026, 1, 1, tzinfo=UTC))
    assert len(targets) == 1


async def test_target_integrator_ignores_missing_hint_or_capability() -> None:
    """Integrator ignores ingress without route hint or capability."""
    store = InMemorySchedulerTargetStore()
    integrator = SchedulerTargetIntegrator(store)
    await integrator.integrate_observation(
        _observation(),
        ObservationIngressContext(
            adapter_id="grpc",
            provider="grpc",
            authenticated=True,
            capabilities=frozenset(),
            delivery_route=DeliveryRouteHint(
                provider="discord",
                provider_subject=ExternalRef("user-1"),
                provider_space_ref=None,
            ),
        ),
    )
    await integrator.integrate_observation(
        _observation(),
        ObservationIngressContext(
            adapter_id="grpc",
            provider="grpc",
            authenticated=True,
            capabilities=frozenset({ObservationCapability.REGISTER_DELIVERY_TARGET}),
            delivery_route=None,
        ),
    )
    assert await store.list_targets(now=datetime(2026, 1, 1, tzinfo=UTC)) == ()
