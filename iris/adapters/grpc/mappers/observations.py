"""Mappers between Iris runtime contracts and gRPC protobuf DTOs."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, assert_never

from iris.adapters.grpc.mappers.common import (
    datetime_from_proto_timestamp,
    metadata_dict,
    raise_mapping_error,
)
from iris.contracts.activity import ActivityKind
from iris.contracts.delivery import DeliveryRouteHint
from iris.contracts.external_refs import ExternalAccountRef, ExternalSpaceRef
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActivityEventObservation,
    ActorMessageObservation,
    IdleTickObservation,
    Observation,
    ObservationContext,
    ObservationKind,
    PresenceSignalObservation,
)
from iris.contracts.presence import PresenceStatus
from iris.contracts.spaces import SpaceKind
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
from iris.generated.iris.api.v1 import identity_pb2, observations_pb2, spaces_pb2
from iris.runtime.auth.principals import ClientKind, ClientPrincipal
from iris.runtime.service import ObservationEnvelope

_ACTOR_SCOPED_ACTIVITY_KINDS = frozenset(
    {
        ActivityKind.ACTOR_TYPING_STARTED,
        ActivityKind.ACTOR_TYPING_STOPPED,
        ActivityKind.VOICE_JOINED,
        ActivityKind.VOICE_LEFT,
    }
)

_GRPC_ADAPTER_ID = "grpc"
_GRPC_ADAPTER_PROVIDER = "grpc"

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from iris.adapters.app_gateway.ports import IdentityResolver, SpaceResolver
    from iris.contracts.spaces import InteractionSpace
    from iris.generated.iris.runtime.v1 import runtime_pb2
    from iris.runtime.ingress.observation_ingress import ObservationCapability


class RuntimeIngressProfile(StrEnum):
    """gRPC SubmitObservation ingress trust profile."""

    EXTERNAL_CLIENT = "external_client"
    TRUSTED_ADAPTER = "trusted_adapter"


def _runtime_ingress_profile(value: RuntimeIngressProfile | str) -> RuntimeIngressProfile:
    try:
        return RuntimeIngressProfile(value)
    except (TypeError, ValueError) as exc:
        raise_mapping_error("invalid runtime ingress profile", cause=exc)


class GrpcRuntimeMapper:
    """Async mapper for gRPC proto DTOs to Iris runtime contracts.

    The mapper resolves ExternalAccountRef into typed Identity at the gRPC
    boundary so cognitive layers never see provider-subject strings.
    """

    def __init__(
        self,
        identity_resolver: IdentityResolver | None = None,
        space_resolver: SpaceResolver | None = None,
        ingress_profile: RuntimeIngressProfile | str = RuntimeIngressProfile.EXTERNAL_CLIENT,
        adapter_capabilities: Iterable[ObservationCapability] | None = None,
    ) -> None:
        """Create mapper with optional resolvers and adapter capabilities.

        Args:
            identity_resolver: Optional identity resolver for ExternalAccountRef.
            space_resolver: Optional space resolver for ExternalSpaceRef.
            ingress_profile: Trust profile for SubmitObservation ingress.
            adapter_capabilities: Capabilities to grant on the trusted
                adapter ingress. Required for TRUSTED_ADAPTER.
        """
        self._identity_resolver = identity_resolver
        self._space_resolver = space_resolver
        profile = _runtime_ingress_profile(ingress_profile)
        self._ingress_profile = profile
        if (
            self._ingress_profile is RuntimeIngressProfile.TRUSTED_ADAPTER
            and adapter_capabilities is None
        ):
            raise_mapping_error("trusted adapter ingress requires explicit capabilities")
        self._adapter_capabilities = frozenset(adapter_capabilities or ())

    async def observation_envelope_from_proto(
        self,
        request: runtime_pb2.SubmitObservationRequest,
        principal: ClientPrincipal | None = None,
    ) -> ObservationEnvelope:
        """Map SubmitObservationRequest proto into ObservationEnvelope.

        Returns:
            ObservationEnvelope: Runtime service input envelope.
        """
        if not request.HasField("observation"):
            raise_mapping_error("observation required")
        correlation_id = CorrelationId(request.correlation_id) if request.correlation_id else None
        observation = await self.observation_from_proto(request.observation)
        if principal is not None and principal.client_kind is ClientKind.TRUSTED_ADAPTER:
            delivery_route = delivery_route_hint_from_context(request.observation.context)
            return ObservationEnvelope.trusted_adapter(
                observation=observation,
                adapter_id=principal.client_id,
                provider=principal.provider,
                capabilities=principal.observation_capabilities,
                correlation_id=correlation_id,
                delivery_route=delivery_route,
            )
        if self._ingress_profile is RuntimeIngressProfile.EXTERNAL_CLIENT:
            return ObservationEnvelope.external_client(
                observation=observation,
                correlation_id=correlation_id,
            )
        delivery_route = delivery_route_hint_from_context(request.observation.context)
        return ObservationEnvelope.trusted_adapter(
            observation=observation,
            adapter_id=_GRPC_ADAPTER_ID,
            provider=_GRPC_ADAPTER_PROVIDER,
            capabilities=self._adapter_capabilities,
            correlation_id=correlation_id,
            delivery_route=delivery_route,
        )

    async def observation_from_proto(
        self,
        observation: observations_pb2.Observation,
    ) -> Observation:
        """Map Observation proto to an Iris Observation contract.

        Returns:
            Observation: kindとpayloadが一致する型付き観測。
        """
        kind = _observation_kind_from_proto(observation.kind)
        _validate_observation_kind_and_payload(observation)
        occurred_at = _datetime_from_timestamp(observation)
        context = await self.observation_context_from_proto(observation.context)
        if kind is ObservationKind.ACTOR_MESSAGE:
            return self._map_actor_message(observation, kind, occurred_at, context)
        if kind is ObservationKind.IDLE_TICK:
            return self._map_idle_tick(observation, kind, occurred_at, context)
        if kind is ObservationKind.ACTIVITY_EVENT:
            return self._map_activity_event(observation, kind, occurred_at, context)
        if kind is ObservationKind.PRESENCE_SIGNAL:
            return self._map_presence_signal(observation, kind, occurred_at, context)
        assert_never(kind)

    @staticmethod
    def _map_actor_message(
        observation: observations_pb2.Observation,
        kind: ObservationKind,
        occurred_at: datetime,
        context: ObservationContext,
    ) -> ActorMessageObservation:
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

    @staticmethod
    def _map_idle_tick(
        observation: observations_pb2.Observation,
        kind: ObservationKind,
        occurred_at: datetime,
        context: ObservationContext,
    ) -> IdleTickObservation:
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

    @staticmethod
    def _map_activity_event(
        observation: observations_pb2.Observation,
        kind: ObservationKind,
        occurred_at: datetime,
        context: ObservationContext,
    ) -> ActivityEventObservation:
        activity_payload = observation.activity_event
        if activity_payload.provider_sequence < 0:
            raise_mapping_error("activity_event.provider_sequence must not be negative")
        activity_kind = _activity_kind_from_proto(activity_payload.activity_kind)
        _require_activity_subject(
            activity_kind=activity_kind,
            context=context,
        )
        return ActivityEventObservation(
            observation_id=ObservationId(observation.observation_id),
            session_id=SessionId(observation.session_id),
            context=context,
            occurred_at=occurred_at,
            kind=kind,
            activity_kind=activity_kind,
            provider_event_id=activity_payload.provider_event_id or None,
            provider_sequence=activity_payload.provider_sequence or None,
            metadata=metadata_dict(activity_payload.metadata),
        )

    @staticmethod
    def _map_presence_signal(
        observation: observations_pb2.Observation,
        kind: ObservationKind,
        occurred_at: datetime,
        context: ObservationContext,
    ) -> PresenceSignalObservation:
        _require_presence_subject(context)
        presence_payload = observation.presence_signal
        expires_at = (
            datetime_from_proto_timestamp(
                presence_payload.expires_at,
                field_name="presence_signal.expires_at",
            )
            if presence_payload.HasField("expires_at")
            else None
        )
        return PresenceSignalObservation(
            observation_id=ObservationId(observation.observation_id),
            session_id=SessionId(observation.session_id),
            context=context,
            occurred_at=occurred_at,
            kind=kind,
            status=_presence_status_from_proto(presence_payload.status),
            expires_at=expires_at,
            metadata=metadata_dict(presence_payload.metadata),
        )

    async def observation_context_from_proto(
        self,
        context: observations_pb2.ObservationContext,
    ) -> ObservationContext:
        """Map ObservationContext proto to Iris ObservationContext.

        Returns:
            ObservationContext: Typed observation context.
        """
        actor, account_id = await self._resolve_actor_from_context(context)
        space_id = await self._resolve_space_from_context(context)

        return ObservationContext(
            actor=actor,
            account_id=account_id,
            device_id=DeviceId(context.device_id) if context.device_id else None,
            space_id=space_id,
            source=context.source or None,
            metadata=metadata_dict(context.metadata),
        )

    async def _resolve_actor_from_context(
        self,
        context: observations_pb2.ObservationContext,
    ) -> tuple[Identity | None, AccountId | None]:
        has_actor = context.HasField("actor")
        has_account_ref = context.HasField("account_ref")
        if has_actor and has_account_ref:
            raise_mapping_error("context must not include both actor and account_ref")
        if has_account_ref and context.account_id:
            raise_mapping_error("context must not include both account_ref and account_id")

        if has_account_ref:
            actor = await self._resolve_account_ref(
                context.account_ref,
                device_id=DeviceId(context.device_id) if context.device_id else None,
            )
        elif has_actor:
            actor = identity_from_proto(context.actor)
            if context.account_id and actor.account_id and context.account_id != actor.account_id:
                raise_mapping_error("context.account_id and actor.account_id do not match")
        else:
            actor = None

        account_id = AccountId(context.account_id) if context.account_id else None
        if actor and actor.account_id:
            account_id = actor.account_id

        return actor, account_id

    async def _resolve_space_from_context(
        self,
        context: observations_pb2.ObservationContext,
    ) -> SpaceId | None:
        has_space_ref = context.HasField("space_ref")
        if has_space_ref:
            if context.space_id:
                raise_mapping_error("context must not include both space_ref and space_id")
            resolved_space = await self._resolve_space_ref(context.space_ref)
            return resolved_space.space_id
        if context.space_id:
            return SpaceId(context.space_id)
        return None

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
            raise_mapping_error("identity resolver is required for account_ref")

        dto = external_account_ref_from_proto(account_ref)
        return await self._identity_resolver.resolve_identity(
            dto,
            device_id=device_id,
        )

    async def _resolve_space_ref(
        self,
        space_ref: spaces_pb2.ExternalSpaceRef,
    ) -> InteractionSpace:
        """Resolve ExternalSpaceRef into an InteractionSpace via the resolver.

        Returns:
            InteractionSpace: Resolved typed space.
        """
        if self._space_resolver is None:
            raise_mapping_error("space resolver is required for space_ref")

        dto = external_space_ref_from_proto(space_ref)

        return await self._space_resolver.resolve_space(dto)


def external_account_ref_from_proto(
    account_ref: identity_pb2.ExternalAccountRef,
) -> ExternalAccountRef:
    """Map ExternalAccountRef proto to DTO.

    Returns:
        ExternalAccountRef: Mapped DTO.
    """
    if not account_ref.provider:
        raise_mapping_error("account_ref.provider is required")
    if not account_ref.provider_subject:
        raise_mapping_error("account_ref.provider_subject is required")
    if not account_ref.display_name:
        raise_mapping_error("account_ref.display_name is required")
    actor_kind = _account_ref_kind_to_contract(account_ref.actor_kind)
    return ExternalAccountRef(
        provider=account_ref.provider,
        provider_subject=ExternalRef(account_ref.provider_subject),
        display_name=account_ref.display_name,
        actor_kind=actor_kind,
        account_id=None,
        metadata=metadata_dict(account_ref.metadata),
    )


def external_space_ref_from_proto(
    space_ref: spaces_pb2.ExternalSpaceRef,
) -> ExternalSpaceRef:
    """Map ExternalSpaceRef proto to DTO.

    Returns:
        ExternalSpaceRef: Mapped DTO.
    """
    if not space_ref.provider:
        raise_mapping_error("space_ref.provider is required")
    if not space_ref.provider_space_ref:
        raise_mapping_error("space_ref.provider_space_ref is required")
    if not space_ref.display_name:
        raise_mapping_error("space_ref.display_name is required")
    if space_ref.space_kind == spaces_pb2.SPACE_KIND_UNSPECIFIED:
        raise_mapping_error("space_ref.space_kind must not be unspecified")

    space_kind = _space_kind_from_proto(space_ref.space_kind)

    return ExternalSpaceRef(
        provider=space_ref.provider,
        provider_space_ref=ExternalRef(space_ref.provider_space_ref),
        display_name=space_ref.display_name,
        space_kind=space_kind,
        metadata=metadata_dict(space_ref.metadata),
    )


def delivery_route_hint_from_context(
    context: observations_pb2.ObservationContext,
) -> DeliveryRouteHint | None:
    """Preserve provider routing fields outside ObservationContext.

    Returns:
        DeliveryRouteHint: provider routing hint。refs がない場合は None。
    """
    provider = _route_provider_from_context(context)
    if provider is None:
        return None
    provider_subject = (
        ExternalRef(context.account_ref.provider_subject)
        if context.HasField("account_ref") and context.account_ref.provider_subject
        else None
    )
    provider_space_ref = (
        ExternalRef(context.space_ref.provider_space_ref)
        if context.HasField("space_ref") and context.space_ref.provider_space_ref
        else None
    )
    display_name = None
    if context.HasField("account_ref") and context.account_ref.display_name:
        display_name = context.account_ref.display_name
    elif context.HasField("space_ref") and context.space_ref.display_name:
        display_name = context.space_ref.display_name
    return DeliveryRouteHint(
        provider=provider,
        provider_subject=provider_subject,
        provider_space_ref=provider_space_ref,
        display_name=display_name,
    )


def _route_provider_from_context(
    context: observations_pb2.ObservationContext,
) -> str | None:
    """Return provider for a delivery route hint when refs are present."""
    account_provider = context.account_ref.provider if context.HasField("account_ref") else ""
    space_provider = context.space_ref.provider if context.HasField("space_ref") else ""
    if account_provider and space_provider and account_provider != space_provider:
        raise_mapping_error("account_ref.provider space_ref.provider mismatch")
    return account_provider or space_provider or None


def identity_from_proto(identity: identity_pb2.Identity) -> Identity:
    """Map Identity proto to Iris Identity.

    Returns:
        Identity: Typed actor identity.
    """
    actor_kind = _actor_kind_from_proto(identity.actor_kind)
    if not identity.actor_id:
        raise_mapping_error("identity.actor_id is required")
    provider = identity.provider or None
    provider_subject = ExternalRef(identity.provider_subject) if identity.provider_subject else None

    # Require provider_subject for external actors
    if actor_kind not in {ActorKind.SYSTEM, ActorKind.IRIS} and not provider_subject:
        raise_mapping_error("identity.provider_subject is required for external actors")

    return Identity(
        actor_id=ActorId(identity.actor_id),
        actor_kind=actor_kind,
        display_name=identity.display_name,
        provider=provider,
        provider_subject=provider_subject,
        account_id=AccountId(identity.account_id) if identity.account_id else None,
        device_id=DeviceId(identity.device_id) if identity.device_id else None,
        metadata=metadata_dict(identity.metadata),
    )


def _datetime_from_timestamp(observation: observations_pb2.Observation) -> datetime:
    if not observation.HasField("occurred_at"):
        raise_mapping_error("occurred_at is required")
    return datetime_from_proto_timestamp(
        observation.occurred_at,
        field_name="occurred_at",
    )


def _validate_observation_kind_and_payload(
    observation: observations_pb2.Observation,
) -> None:
    expected_payload_by_kind = {
        observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE: "actor_message",
        observations_pb2.OBSERVATION_KIND_IDLE_TICK: "idle_tick",
        observations_pb2.OBSERVATION_KIND_ACTIVITY_EVENT: "activity_event",
        observations_pb2.OBSERVATION_KIND_PRESENCE_SIGNAL: "presence_signal",
    }
    try:
        expected_payload = expected_payload_by_kind[observation.kind]
    except KeyError:
        raise_mapping_error(f"unsupported or unspecified observation kind: {observation.kind}")
    actual_payload = observation.WhichOneof("payload")
    if actual_payload != expected_payload:
        raise_mapping_error(
            f"observation kind requires {expected_payload} payload, got {actual_payload or 'none'}"
        )


def _require_presence_subject(context: ObservationContext) -> None:
    if context.actor is None and context.account_id is None:
        raise_mapping_error("presence_signal requires actor or account_id")


def _require_activity_subject(
    *,
    activity_kind: ActivityKind,
    context: ObservationContext,
) -> None:
    if (
        activity_kind in _ACTOR_SCOPED_ACTIVITY_KINDS
        and context.actor is None
        and context.account_id is None
    ):
        raise_mapping_error(f"{activity_kind.value} requires actor or account_id")


def _observation_kind_from_proto(
    kind: observations_pb2.ObservationKind.ValueType,
) -> ObservationKind:
    mapping = {
        observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE: ObservationKind.ACTOR_MESSAGE,
        observations_pb2.OBSERVATION_KIND_IDLE_TICK: ObservationKind.IDLE_TICK,
        observations_pb2.OBSERVATION_KIND_ACTIVITY_EVENT: ObservationKind.ACTIVITY_EVENT,
        observations_pb2.OBSERVATION_KIND_PRESENCE_SIGNAL: ObservationKind.PRESENCE_SIGNAL,
    }
    try:
        return mapping[kind]
    except KeyError:
        raise_mapping_error(f"unsupported or unspecified observation kind: {kind}")


def _activity_kind_from_proto(
    kind: observations_pb2.ActivityKind.ValueType,
) -> ActivityKind:
    mapping = {
        observations_pb2.ACTIVITY_KIND_ACTOR_TYPING_STARTED: ActivityKind.ACTOR_TYPING_STARTED,
        observations_pb2.ACTIVITY_KIND_ACTOR_TYPING_STOPPED: ActivityKind.ACTOR_TYPING_STOPPED,
        observations_pb2.ACTIVITY_KIND_APP_OPENED: ActivityKind.APP_OPENED,
        observations_pb2.ACTIVITY_KIND_APP_CLOSED: ActivityKind.APP_CLOSED,
        observations_pb2.ACTIVITY_KIND_VOICE_JOINED: ActivityKind.VOICE_JOINED,
        observations_pb2.ACTIVITY_KIND_VOICE_LEFT: ActivityKind.VOICE_LEFT,
        observations_pb2.ACTIVITY_KIND_SYSTEM_INTERACTION: ActivityKind.SYSTEM_INTERACTION,
    }
    try:
        return mapping[kind]
    except KeyError:
        raise_mapping_error(f"unsupported or unspecified activity kind: {kind}")


def _presence_status_from_proto(
    status: observations_pb2.PresenceStatus.ValueType,
) -> PresenceStatus:
    mapping = {
        observations_pb2.PRESENCE_STATUS_UNKNOWN: PresenceStatus.UNKNOWN,
        observations_pb2.PRESENCE_STATUS_ONLINE: PresenceStatus.ONLINE,
        observations_pb2.PRESENCE_STATUS_OFFLINE: PresenceStatus.OFFLINE,
        observations_pb2.PRESENCE_STATUS_AWAY: PresenceStatus.AWAY,
        observations_pb2.PRESENCE_STATUS_IDLE: PresenceStatus.IDLE,
        observations_pb2.PRESENCE_STATUS_DO_NOT_DISTURB: PresenceStatus.DO_NOT_DISTURB,
        observations_pb2.PRESENCE_STATUS_INVISIBLE: PresenceStatus.INVISIBLE,
    }
    try:
        return mapping[status]
    except KeyError:
        raise_mapping_error(f"unsupported or unspecified presence status: {status}")


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
        raise_mapping_error(f"unsupported or unspecified actor kind: {kind}")


def _space_kind_from_proto(kind: spaces_pb2.SpaceKind.ValueType) -> SpaceKind:
    mapping = {
        spaces_pb2.SPACE_KIND_DIRECT_MESSAGE: SpaceKind.DIRECT_MESSAGE,
        spaces_pb2.SPACE_KIND_TEXT_CHANNEL: SpaceKind.TEXT_CHANNEL,
        spaces_pb2.SPACE_KIND_THREAD: SpaceKind.THREAD,
        spaces_pb2.SPACE_KIND_VOICE_CHANNEL: SpaceKind.VOICE_CHANNEL,
        spaces_pb2.SPACE_KIND_ROOM: SpaceKind.ROOM,
        spaces_pb2.SPACE_KIND_BROADCAST: SpaceKind.BROADCAST,
    }
    try:
        return mapping[kind]
    except KeyError:
        raise_mapping_error(f"unsupported or unspecified space kind: {kind}")


def _account_ref_kind_to_contract(kind: identity_pb2.ActorKind.ValueType) -> ActorKind:
    """Map account_ref actor_kind to contract, defaulting UNSPECIFIED to HUMAN.

    Returns:
        ActorKind: Contract actor kind (HUMAN for UNSPECIFIED, otherwise mapped).
    """
    if kind == identity_pb2.ACTOR_KIND_UNSPECIFIED:
        return ActorKind.HUMAN
    return _actor_kind_from_proto(kind)
