"""ObservationEnvelope ingress factory tests."""

from __future__ import annotations

from datetime import UTC, datetime

from iris.contracts.delivery import DeliveryRouteHint
from iris.contracts.observations import ActorMessageObservation, ObservationContext, ObservationKind
from iris.core.ids import CorrelationId, ExternalRef, ObservationId, SessionId
from iris.runtime.ingress.observation_ingress import ObservationCapability
from iris.runtime.service import ObservationEnvelope

_OCCURRED_AT = datetime(2026, 6, 24, 10, 0, tzinfo=UTC)


def test_external_client_factory_returns_unauthenticated_empty_capabilities() -> None:
    """External client ingress is unauthenticated and capability-free."""
    envelope = ObservationEnvelope.external_client(
        observation=_message_observation(),
        correlation_id=CorrelationId("corr-1"),
    )

    assert not envelope.ingress.authenticated
    assert envelope.ingress.adapter_id == "external_client"
    assert envelope.ingress.provider is None
    assert envelope.ingress.capabilities == frozenset()
    assert envelope.ingress.delivery_route is None


def test_trusted_adapter_factory_preserves_only_supplied_capabilities() -> None:
    """Trusted adapter ingress does not add implicit capabilities."""
    route = DeliveryRouteHint(
        provider="discord",
        provider_subject=ExternalRef("user-1"),
        provider_space_ref=ExternalRef("channel-1"),
        display_name="Mina",
    )

    envelope = ObservationEnvelope.trusted_adapter(
        observation=_message_observation(),
        adapter_id="grpc",
        provider="discord",
        capabilities={ObservationCapability.REACT_TO_ACTIVITY},
        delivery_route=route,
    )

    assert envelope.ingress.authenticated
    assert envelope.ingress.adapter_id == "grpc"
    assert envelope.ingress.provider == "discord"
    assert envelope.ingress.capabilities == frozenset({ObservationCapability.REACT_TO_ACTIVITY})
    assert envelope.ingress.delivery_route == route


def _message_observation() -> ActorMessageObservation:
    return ActorMessageObservation(
        observation_id=ObservationId("obs-1"),
        session_id=SessionId("session-1"),
        context=ObservationContext(source="test"),
        occurred_at=_OCCURRED_AT,
        kind=ObservationKind.ACTOR_MESSAGE,
        text="hello",
    )
