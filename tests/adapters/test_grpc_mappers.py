"""Tests for gRPC runtime DTO mappers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.adapters.grpc.mappers import (
    GrpcMappingError,
    observation_envelope_from_proto,
    observation_from_proto,
    runtime_response_to_proto,
    timestamp_from_datetime,
)
from iris.contracts.actions import PresentedOutput
from iris.contracts.identity import ActorKind
from iris.contracts.observations import ActorMessageObservation, IdleTickObservation
from iris.core.ids import (
    AccountId,
    ActorId,
    CorrelationId,
    DeviceId,
    ExternalRef,
    ObservationId,
    SessionId,
    SpaceId,
)
from iris.generated.iris.api.v1 import identity_pb2, observations_pb2
from iris.generated.iris.runtime.v1 import runtime_pb2
from iris.runtime.service import RuntimeResponse
from tests.helpers.approx import approx

_OCCURRED_AT = datetime(2026, 6, 5, 12, 30, tzinfo=UTC)


def test_actor_message_proto_maps_to_observation_envelope() -> None:
    """ActorMessage protoがObservationEnvelopeへmapされることを確認する。"""
    request = runtime_pb2.SubmitObservationRequest(
        correlation_id="corr-1",
        observation=_actor_message_proto(),
    )

    envelope = observation_envelope_from_proto(request)

    assert envelope.correlation_id == CorrelationId("corr-1")
    assert isinstance(envelope.observation, ActorMessageObservation)
    assert envelope.observation.observation_id == ObservationId("obs-1")
    assert envelope.observation.session_id == SessionId("session-1")
    assert envelope.observation.occurred_at == _OCCURRED_AT
    assert envelope.observation.text == "hello grpc"
    assert envelope.observation.external_message_id == ExternalRef("message-1")


def test_idle_tick_proto_maps_to_observation() -> None:
    """IdleTick protoがIdleTickObservationへmapされることを確認する。"""
    observation = observation_from_proto(
        observations_pb2.Observation(
            observation_id="obs-idle",
            session_id="session-1",
            kind=observations_pb2.OBSERVATION_KIND_IDLE_TICK,
            occurred_at=timestamp_from_datetime(_OCCURRED_AT),
            idle_tick=observations_pb2.IdleTickPayload(reason="quiet", idle_seconds=12.5),
        )
    )

    assert isinstance(observation, IdleTickObservation)
    assert observation.reason == "quiet"
    assert observation.idle_seconds == approx(12.5)


def test_observation_context_actor_maps_to_identity() -> None:
    """ObservationContext actor protoがIdentityへmapされることを確認する。"""
    observation = observation_from_proto(_actor_message_proto())

    assert isinstance(observation, ActorMessageObservation)
    actor = observation.context.actor
    assert actor is not None
    assert actor.actor_id == ActorId("actor-1")
    assert actor.actor_kind == ActorKind.HUMAN
    assert actor.display_name == "Mina"
    assert actor.provider == "test"
    assert actor.provider_subject == ExternalRef("provider-actor-1")
    assert actor.account_id == AccountId("account-actor")
    assert actor.device_id == DeviceId("device-actor")
    assert actor.metadata == {"role": "tester"}
    assert observation.context.account_id == AccountId("account-1")
    assert observation.context.device_id == DeviceId("device-1")
    assert observation.context.space_id == SpaceId("space-1")
    assert observation.context.source == "grpc-test"
    assert observation.context.metadata == {"trace_id": "abc-123"}


def test_runtime_response_maps_to_proto() -> None:
    """RuntimeResponseがSubmitObservationResponse protoへmapされることを確認する。"""
    response = runtime_response_to_proto(
        RuntimeResponse(
            output=PresentedOutput(
                text="hello",
                style_hint="plain",
                emotion_hint="calm",
                expression_hint="smile",
                delay_ms=10,
                priority=3,
                interruptible=False,
            ),
            correlation_id=CorrelationId("corr-1"),
        )
    )

    assert response.correlation_id == "corr-1"
    assert response.output.text == "hello"
    assert response.output.style_hint == "plain"
    assert response.output.emotion_hint == "calm"
    assert response.output.expression_hint == "smile"
    assert response.output.delay_ms == 10
    assert response.output.priority == 3
    assert response.output.interruptible is False


def test_invalid_observation_kind_raises_mapping_error() -> None:
    """Unsupported/unspecified kindがGrpcMappingErrorになることを確認する。"""
    request = _actor_message_proto()
    request.kind = observations_pb2.OBSERVATION_KIND_UNSPECIFIED

    with pytest.raises(GrpcMappingError, match="unsupported or unspecified observation kind"):
        observation_from_proto(request)


def test_actor_message_kind_without_payload_raises_mapping_error() -> None:
    """actor_message kindでpayloadがない場合にmapping errorになることを確認する。"""
    request = observations_pb2.Observation(
        observation_id="obs-1",
        session_id="session-1",
        kind=observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE,
        occurred_at=timestamp_from_datetime(_OCCURRED_AT),
    )

    with pytest.raises(GrpcMappingError, match="requires actor_message payload"):
        observation_from_proto(request)


def test_idle_tick_kind_without_payload_raises_mapping_error() -> None:
    """idle_tick kindでpayloadがない場合にmapping errorになることを確認する。"""
    request = observations_pb2.Observation(
        observation_id="obs-1",
        session_id="session-1",
        kind=observations_pb2.OBSERVATION_KIND_IDLE_TICK,
        occurred_at=timestamp_from_datetime(_OCCURRED_AT),
    )

    with pytest.raises(GrpcMappingError, match="requires idle_tick payload"):
        observation_from_proto(request)


def _actor_message_proto() -> observations_pb2.Observation:
    """Actor message proto test fixtureを作る。

    Returns:
        observations_pb2.Observation: Actor message observation DTO。
    """
    return observations_pb2.Observation(
        observation_id="obs-1",
        session_id="session-1",
        kind=observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE,
        occurred_at=timestamp_from_datetime(_OCCURRED_AT),
        context=observations_pb2.ObservationContext(
            actor=identity_pb2.Identity(
                actor_id="actor-1",
                actor_kind=identity_pb2.ACTOR_KIND_HUMAN,
                display_name="Mina",
                provider="test",
                provider_subject="provider-actor-1",
                account_id="account-actor",
                device_id="device-actor",
                metadata={"role": "tester"},
            ),
            account_id="account-1",
            device_id="device-1",
            space_id="space-1",
            source="grpc-test",
            metadata={"trace_id": "abc-123"},
        ),
        actor_message=observations_pb2.ActorMessagePayload(
            text="hello grpc",
            external_message_id="message-1",
        ),
    )
