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

    from iris.adapters.app_gateway.ports import IdentityResolver
    from iris.contracts.actions import PresentedOutput
    from iris.runtime.service import RuntimeResponse


class GrpcMappingError(ValueError):
    """Raised when gRPC DTOs cannot be mapped to Iris contracts."""


class GrpcRuntimeMapper:
    """Async mapper for gRPC proto DTOs to Iris runtime contracts.

    The mapper resolves ExternalAccountRef into typed Identity at the gRPC
    boundary so cognitive layers never see provider-subject strings.
    """

    def __init__(self, identity_resolver: IdentityResolver | None = None) -> None:
        """Create mapper with an optional IdentityResolver dependency."""
        self._identity_resolver = identity_resolver

    async def observation_envelope_from_proto(
        self,
        request: runtime_pb2.SubmitObservationRequest,
    ) -> ObservationEnvelope:
        """Map SubmitObservationRequest proto to ObservationEnvelope.

        Returns:
            ObservationEnvelope: Runtime service input envelope.
        """
        if not request.HasField("observation"):
            _raise_mapping_error("observation is required")
        correlation_id = CorrelationId(request.correlation_id) if request.correlation_id else None
        observation = await self.observation_from_proto(request.observation)
        return ObservationEnvelope(
            observation=observation,
            correlation_id=correlation_id,
        )

    async def observation_from_proto(
        self,
        observation: observations_pb2.Observation,
    ) -> Observation:
        """Map Observation proto to an Iris Observation contract.

        Returns:
            Observation: ActorMessageObservation or IdleTickObservation.
        """
        kind = _observation_kind_from_proto(observation.kind)
        occurred_at = _datetime_from_timestamp(observation)
        context = await self.observation_context_from_proto(observation.context)
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

    async def observation_context_from_proto(
        self,
        context: observations_pb2.ObservationContext,
    ) -> ObservationContext:
        """Map ObservationContext proto to Iris ObservationContext.

        Returns:
            ObservationContext: Typed observation context.
        """
        has_actor = context.HasField("actor")
        has_account_ref = context.HasField("account_ref")
        if has_actor and has_account_ref:
            _raise_mapping_error("context must not include both actor and account_ref")
        if has_account_ref and context.account_id:
            _raise_mapping_error("context must not include both account_ref and account_id")

        if has_account_ref:
            actor = await self._resolve_account_ref(
                context.account_ref,
                device_id=DeviceId(context.device_id) if context.device_id else None,
            )
        elif has_actor:
            actor = identity_from_proto(context.actor)
            if context.account_id and actor.account_id and context.account_id != actor.account_id:
                _raise_mapping_error("context.account_id and actor.account_id do not match")
        else:
            actor = None

        account_id = context.account_id
        if actor and actor.account_id:
            account_id = actor.account_id

        return ObservationContext(
            actor=actor,
            account_id=AccountId(account_id) if account_id else None,
            device_id=DeviceId(context.device_id) if context.device_id else None,
            space_id=SpaceId(context.space_id) if context.space_id else None,
            source=context.source or None,
            metadata=dict(context.metadata.items()),
        )

    async def _resolve_account_ref(
        self,
        account_ref: identity_pb2.ExternalAccountRef,
        *,
        device_id: DeviceId | None,
    ) -> Identity:
        """Resolve ExternalAccountRef into a typed Identity via the resolver.

        Returns:
            Identity: Resolved typed actor identity.
        """
        if self._identity_resolver is None:
            _raise_mapping_error("identity resolver is required for account_ref")
        if not account_ref.provider:
            _raise_mapping_error("account_ref.provider is required")
        if not account_ref.provider_subject:
            _raise_mapping_error("account_ref.provider_subject is required")
        if not account_ref.display_name:
            _raise_mapping_error("account_ref.display_name is required")
        actor_kind = _account_ref_kind_to_contract(account_ref.actor_kind)
        return await self._identity_resolver.resolve_identity(
            provider=account_ref.provider,
            provider_subject=ExternalRef(account_ref.provider_subject),
            display_name=account_ref.display_name,
            actor_kind=actor_kind,
            account_id=None,
            device_id=device_id,
            metadata=dict(account_ref.metadata.items()),
        )


def identity_from_proto(identity: identity_pb2.Identity) -> Identity:
    """Map Identity proto to Iris Identity.

    Returns:
        Identity: Typed actor identity.
    """
    actor_kind = _actor_kind_from_proto(identity.actor_kind)
    if not identity.actor_id:
        _raise_mapping_error("identity.actor_id is required")
    provider = identity.provider or None
    provider_subject = ExternalRef(identity.provider_subject) if identity.provider_subject else None

    # Require provider_subject for external actors
    if actor_kind not in {ActorKind.SYSTEM, ActorKind.IRIS} and not provider_subject:
        _raise_mapping_error("identity.provider_subject is required for external actors")

    return Identity(
        actor_id=ActorId(identity.actor_id),
        actor_kind=actor_kind,
        display_name=identity.display_name,
        provider=provider,
        provider_subject=provider_subject,
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


def _account_ref_kind_to_contract(kind: identity_pb2.ActorKind.ValueType) -> ActorKind:
    """Map account_ref actor_kind to contract, defaulting UNSPECIFIED to HUMAN.

    Returns:
        ActorKind: Contract actor kind (HUMAN for UNSPECIFIED, otherwise mapped).
    """
    if kind == identity_pb2.ACTOR_KIND_UNSPECIFIED:
        return ActorKind.HUMAN
    return _actor_kind_from_proto(kind)


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
