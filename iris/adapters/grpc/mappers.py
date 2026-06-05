"""Mappers between Iris runtime contracts and gRPC protobuf DTOs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, NoReturn

from google.protobuf.timestamp_pb2 import Timestamp

from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActorMessageObservation,
    IdleTickObservation,
    Observation,
    ObservationContext,
    ObservationKind,
)
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
from iris.generated.iris.api.v1 import identity_pb2, observations_pb2, outputs_pb2
from iris.generated.iris.runtime.v1 import runtime_pb2
from iris.runtime.service import ObservationEnvelope

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.contracts.actions import PresentedOutput
    from iris.runtime.service import RuntimeResponse


class GrpcMappingError(ValueError):
    """Raised when gRPC DTOs cannot be mapped to Iris contracts."""


def observation_envelope_from_proto(
    request: runtime_pb2.SubmitObservationRequest,
) -> ObservationEnvelope:
    """Map SubmitObservationRequest proto to ObservationEnvelope.

    Returns:
        ObservationEnvelope: Runtime service input envelope.
    """
    if not request.HasField("observation"):
        _raise_mapping_error("observation is required")
    correlation_id = CorrelationId(request.correlation_id) if request.correlation_id else None
    return ObservationEnvelope(
        observation=observation_from_proto(request.observation),
        correlation_id=correlation_id,
    )


def observation_from_proto(observation: observations_pb2.Observation) -> Observation:
    """Map Observation proto to an Iris Observation contract.

    Returns:
        Observation: ActorMessageObservation or IdleTickObservation.
    """
    kind = _observation_kind_from_proto(observation.kind)
    occurred_at = _datetime_from_timestamp(observation)
    context = observation_context_from_proto(observation.context)
    if kind is ObservationKind.ACTOR_MESSAGE:
        _require_payload(observation, "actor_message", kind)
        actor_payload = observation.actor_message
        return ActorMessageObservation(
            observation_id=ObservationId(observation.observation_id),
            session_id=SessionId(observation.session_id),
            context=context,
            occurred_at=occurred_at,
            kind=kind,
            text=actor_payload.text,
            external_message_id=(
                ExternalRef(actor_payload.external_message_id)
                if actor_payload.external_message_id
                else None
            ),
        )
    if kind is ObservationKind.IDLE_TICK:
        _require_payload(observation, "idle_tick", kind)
        idle_payload = observation.idle_tick
        return IdleTickObservation(
            observation_id=ObservationId(observation.observation_id),
            session_id=SessionId(observation.session_id),
            context=context,
            occurred_at=occurred_at,
            kind=kind,
            reason=idle_payload.reason or None,
            idle_seconds=idle_payload.idle_seconds,
        )
    return _raise_mapping_error(f"unsupported observation kind: {kind.value}")


def observation_context_from_proto(
    context: observations_pb2.ObservationContext,
) -> ObservationContext:
    """Map ObservationContext proto to Iris ObservationContext.

    Returns:
        ObservationContext: Typed observation context.
    """
    actor = identity_from_proto(context.actor) if context.HasField("actor") else None
    return ObservationContext(
        actor=actor,
        account_id=AccountId(context.account_id) if context.account_id else None,
        device_id=DeviceId(context.device_id) if context.device_id else None,
        space_id=SpaceId(context.space_id) if context.space_id else None,
        source=context.source or None,
    )


def identity_from_proto(identity: identity_pb2.Identity) -> Identity:
    """Map Identity proto to Iris Identity.

    Returns:
        Identity: Typed actor identity.
    """
    actor_kind = _actor_kind_from_proto(identity.actor_kind)
    if not identity.actor_id:
        _raise_mapping_error("identity.actor_id is required")
    if not identity.provider_subject:
        _raise_mapping_error("identity.provider_subject is required")
    return Identity(
        actor_id=ActorId(identity.actor_id),
        actor_kind=actor_kind,
        display_name=identity.display_name,
        provider=identity.provider,
        provider_subject=ExternalRef(identity.provider_subject),
        account_id=AccountId(identity.account_id) if identity.account_id else None,
        device_id=DeviceId(identity.device_id) if identity.device_id else None,
        metadata=_metadata_dict(identity.metadata),
    )


def runtime_response_to_proto(
    response: RuntimeResponse,
) -> runtime_pb2.SubmitObservationResponse:
    """Map RuntimeResponse to SubmitObservationResponse proto.

    Returns:
        runtime_pb2.SubmitObservationResponse: Proto response.
    """
    return runtime_pb2.SubmitObservationResponse(
        correlation_id=str(response.correlation_id or ""),
        output=presented_output_to_proto(response.output),
    )


def presented_output_to_proto(output: PresentedOutput) -> outputs_pb2.PresentedOutput:
    """Map PresentedOutput contract to proto DTO.

    Returns:
        outputs_pb2.PresentedOutput: Proto presented output.
    """
    return outputs_pb2.PresentedOutput(
        text=output.text or "",
        style_hint=output.style_hint or "",
        emotion_hint=output.emotion_hint or "",
        expression_hint=output.expression_hint or "",
        delay_ms=output.delay_ms,
        priority=output.priority,
        interruptible=output.interruptible,
    )


def timestamp_from_datetime(value: datetime) -> Timestamp:
    """Map timezone-aware datetime to protobuf Timestamp.

    Returns:
        Timestamp: Proto timestamp.
    """
    timestamp = Timestamp()
    timestamp.FromDatetime(value)
    return timestamp


def _datetime_from_timestamp(observation: observations_pb2.Observation) -> datetime:
    if not observation.HasField("occurred_at"):
        _raise_mapping_error("occurred_at is required")
    try:
        occurred_at = observation.occurred_at.ToDatetime(tzinfo=UTC)
    except (OverflowError, ValueError) as exc:
        _raise_mapping_error("occurred_at is invalid", cause=exc)
    if occurred_at.tzinfo is None:
        _raise_mapping_error("occurred_at must be timezone-aware")
    return occurred_at


def _require_payload(
    observation: observations_pb2.Observation,
    payload_name: str,
    kind: ObservationKind,
) -> None:
    if observation.WhichOneof("payload") != payload_name:
        _raise_mapping_error(f"{kind.value} requires {payload_name} payload")


def _observation_kind_from_proto(
    kind: observations_pb2.ObservationKind.ValueType,
) -> ObservationKind:
    mapping = {
        observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE: ObservationKind.ACTOR_MESSAGE,
        observations_pb2.OBSERVATION_KIND_IDLE_TICK: ObservationKind.IDLE_TICK,
    }
    try:
        return mapping[kind]
    except KeyError:
        _raise_mapping_error(f"unsupported or unspecified observation kind: {kind}")


def _actor_kind_from_proto(kind: identity_pb2.ActorKind.ValueType) -> ActorKind:
    mapping = {
        identity_pb2.ACTOR_KIND_HUMAN: ActorKind.HUMAN,
        identity_pb2.ACTOR_KIND_DEVICE: ActorKind.DEVICE,
        identity_pb2.ACTOR_KIND_SERVICE: ActorKind.SERVICE,
        identity_pb2.ACTOR_KIND_SYSTEM: ActorKind.SYSTEM,
        identity_pb2.ACTOR_KIND_IRIS: ActorKind.IRIS,
    }
    try:
        return mapping[kind]
    except KeyError:
        _raise_mapping_error(f"unsupported or unspecified actor kind: {kind}")


def _metadata_dict(metadata: Mapping[str, str]) -> dict[str, str]:
    return dict(metadata.items())


def _raise_mapping_error(message: str, *, cause: BaseException | None = None) -> NoReturn:
    """Raise GrpcMappingError with a caller-provided message.

    Raises:
        GrpcMappingError: Always raised.
    """
    if cause is None:
        raise GrpcMappingError(message)
    raise GrpcMappingError(message) from cause
