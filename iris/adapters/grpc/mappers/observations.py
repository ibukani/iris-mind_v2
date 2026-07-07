"""Mappers between Iris runtime contracts and gRPC protobuf DTOs."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from iris.adapters.grpc.mappers.common import (
    datetime_from_proto_timestamp,
    metadata_dict,
    raise_mapping_error,
)
from iris.adapters.grpc.mappers.references import (
    external_account_ref_from_proto,
    external_space_ref_from_proto,
    identity_from_proto,
)
from iris.adapters.grpc.mappers.routing import delivery_route_hint_from_context
from iris.contracts.activity import ActivityKind
from iris.contracts.observations import (
    ActivityEventObservation,
    ActorMessageObservation,
    IdleTickObservation,
    Observation,
    ObservationContext,
    ObservationKind,
    PresenceSignalObservation,
    UserFeedbackKind,
    UserFeedbackObservation,
)
from iris.contracts.presence import PresenceStatus
from iris.core.ids import (
    AccountId,
    ActionId,
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
        ActivityKind.ACTOR_INPUT_STARTED,
        ActivityKind.ACTOR_INPUT_STOPPED,
    }
)

_GRPC_ADAPTER_ID = "grpc"
_GRPC_ADAPTER_PROVIDER = "grpc"

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from datetime import datetime

    from iris.adapters.app_gateway.ports import IdentityResolver, SpaceResolver
    from iris.contracts.identity import Identity
    from iris.contracts.spaces import InteractionSpace
    from iris.generated.iris.runtime.v1 import runtime_pb2
    from iris.runtime.ingress.observation_ingress import ObservationCapability

    ObservationMapper = Callable[
        [observations_pb2.Observation, ObservationKind, datetime, ObservationContext],
        Observation,
    ]


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
        mapper = self._observation_mapper_for(kind)
        return mapper(observation, kind, occurred_at, context)

    def _observation_mapper_for(self, kind: ObservationKind) -> ObservationMapper:
        """Observation kindに対応するpayload mapperを返す。

        Returns:
            対応するpayload mapper。
        """
        mappers: dict[ObservationKind, ObservationMapper] = {
            ObservationKind.ACTOR_MESSAGE: self._map_actor_message,
            ObservationKind.IDLE_TICK: self._map_idle_tick,
            ObservationKind.ACTIVITY_EVENT: self._map_activity_event,
            ObservationKind.PRESENCE_SIGNAL: self._map_presence_signal,
            ObservationKind.USER_FEEDBACK: self._map_user_feedback,
        }
        return mappers[kind]

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

    @staticmethod
    def _map_user_feedback(
        observation: observations_pb2.Observation,
        kind: ObservationKind,
        occurred_at: datetime,
        context: ObservationContext,
    ) -> UserFeedbackObservation:
        feedback_payload = observation.user_feedback
        if not feedback_payload.text.strip():
            raise_mapping_error("user_feedback.text must not be blank")
        return UserFeedbackObservation(
            observation_id=ObservationId(observation.observation_id),
            session_id=SessionId(observation.session_id),
            context=context,
            occurred_at=occurred_at,
            kind=kind,
            feedback_kind=_user_feedback_kind_from_proto(feedback_payload.feedback_kind),
            text=feedback_payload.text,
            target_observation_id=(
                ObservationId(feedback_payload.target_observation_id)
                if feedback_payload.target_observation_id
                else None
            ),
            target_action_id=(
                ActionId(feedback_payload.target_action_id)
                if feedback_payload.target_action_id
                else None
            ),
            target_external_message_id=(
                ExternalRef(feedback_payload.target_external_message_id)
                if feedback_payload.target_external_message_id
                else None
            ),
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
        observations_pb2.OBSERVATION_KIND_USER_FEEDBACK: "user_feedback",
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
        observations_pb2.OBSERVATION_KIND_USER_FEEDBACK: ObservationKind.USER_FEEDBACK,
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
        observations_pb2.ACTIVITY_KIND_ACTOR_INPUT_STARTED: ActivityKind.ACTOR_INPUT_STARTED,
        observations_pb2.ACTIVITY_KIND_ACTOR_INPUT_STOPPED: ActivityKind.ACTOR_INPUT_STOPPED,
        observations_pb2.ACTIVITY_KIND_APP_OUTPUT_STARTED: ActivityKind.APP_OUTPUT_STARTED,
        observations_pb2.ACTIVITY_KIND_APP_OUTPUT_STOPPED: ActivityKind.APP_OUTPUT_STOPPED,
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


def _user_feedback_kind_from_proto(
    kind: observations_pb2.UserFeedbackKind.ValueType,
) -> UserFeedbackKind:
    mapping = {
        observations_pb2.USER_FEEDBACK_KIND_POSITIVE: UserFeedbackKind.POSITIVE,
        observations_pb2.USER_FEEDBACK_KIND_NEGATIVE: UserFeedbackKind.NEGATIVE,
        observations_pb2.USER_FEEDBACK_KIND_STYLE_PREFERENCE: UserFeedbackKind.STYLE_PREFERENCE,
        observations_pb2.USER_FEEDBACK_KIND_CORRECTION: UserFeedbackKind.CORRECTION,
        observations_pb2.USER_FEEDBACK_KIND_OTHER: UserFeedbackKind.OTHER,
    }
    try:
        return mapping[kind]
    except KeyError:
        raise_mapping_error(f"unsupported or unspecified user feedback kind: {kind}")
