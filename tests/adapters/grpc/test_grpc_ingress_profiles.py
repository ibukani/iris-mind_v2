"""gRPC SubmitObservation ingress profile tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, override

import pytest

from iris.adapters.app_gateway.fake_resolvers import FakeIdentityResolver
from iris.adapters.app_gateway.ports import SpaceResolver
from iris.adapters.grpc.mappers import (
    GrpcMappingError,
    GrpcRuntimeMapper,
    RuntimeIngressProfile,
    timestamp_from_datetime,
)
from iris.contracts.spaces import InteractionSpace
from iris.core.ids import SpaceId
from iris.generated.iris.api.v1 import identity_pb2, observations_pb2, spaces_pb2
from iris.generated.iris.runtime.v1 import runtime_pb2
from iris.runtime.ingress.observation_ingress import ObservationCapability

if TYPE_CHECKING:
    from iris.contracts.external_refs import ExternalSpaceRef


_OCCURRED_AT = datetime(2026, 6, 24, 9, 0, tzinfo=UTC)


@pytest.mark.anyio
async def test_default_submit_observation_ingress_is_external_client_safe() -> None:
    """Default gRPC SubmitObservation is unauthenticated and capability-free."""
    mapper = GrpcRuntimeMapper(
        identity_resolver=FakeIdentityResolver(),
        space_resolver=_RecordingSpaceResolver(),
    )

    envelope = await mapper.observation_envelope_from_proto(_request_with_refs())

    assert not envelope.ingress.authenticated
    assert envelope.ingress.adapter_id == "external_client"
    assert envelope.ingress.capabilities == frozenset()
    assert envelope.ingress.delivery_route is None
    assert envelope.observation.context.actor is not None
    assert envelope.observation.context.space_id == "resolved-space-discord-channel-1"


def test_trusted_adapter_profile_requires_explicit_capabilities() -> None:
    """Trusted gRPC adapter ingress must not silently grant all capabilities."""
    with pytest.raises(GrpcMappingError, match="explicit capabilities"):
        GrpcRuntimeMapper(ingress_profile=RuntimeIngressProfile.TRUSTED_ADAPTER)


@pytest.mark.anyio
async def test_trusted_adapter_profile_preserves_explicit_capabilities_and_route() -> None:
    """Trusted profile keeps only supplied capabilities and delivery route hints."""
    mapper = GrpcRuntimeMapper(
        identity_resolver=FakeIdentityResolver(),
        space_resolver=_RecordingSpaceResolver(),
        ingress_profile=RuntimeIngressProfile.TRUSTED_ADAPTER,
        adapter_capabilities={ObservationCapability.INTEGRATE_ACTIVITY},
    )

    envelope = await mapper.observation_envelope_from_proto(_request_with_refs())

    assert envelope.ingress.authenticated
    assert envelope.ingress.capabilities == frozenset({ObservationCapability.INTEGRATE_ACTIVITY})
    assert envelope.ingress.delivery_route is not None
    assert envelope.ingress.delivery_route.provider == "discord"
    assert envelope.ingress.delivery_route.provider_subject == "user-1"
    assert envelope.ingress.delivery_route.provider_space_ref == "channel-1"


def _request_with_refs() -> runtime_pb2.SubmitObservationRequest:
    return runtime_pb2.SubmitObservationRequest(
        correlation_id="corr-1",
        observation=observations_pb2.Observation(
            observation_id="obs-1",
            session_id="session-1",
            kind=observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE,
            occurred_at=timestamp_from_datetime(_OCCURRED_AT),
            context=observations_pb2.ObservationContext(
                account_ref=identity_pb2.ExternalAccountRef(
                    provider="discord",
                    provider_subject="user-1",
                    display_name="Mina",
                ),
                space_ref=spaces_pb2.ExternalSpaceRef(
                    provider="discord",
                    provider_space_ref="channel-1",
                    display_name="General",
                    space_kind=spaces_pb2.SPACE_KIND_TEXT_CHANNEL,
                ),
            ),
            actor_message=observations_pb2.ActorMessagePayload(text="hello"),
        ),
    )


class _RecordingSpaceResolver(SpaceResolver):
    @override
    async def resolve_space(self, space_ref: ExternalSpaceRef) -> InteractionSpace:
        return InteractionSpace(
            space_id=SpaceId(f"resolved-space-{space_ref.provider}-{space_ref.provider_space_ref}"),
            space_kind=space_ref.space_kind,
            display_name=space_ref.display_name,
            metadata=dict(space_ref.metadata),
        )
