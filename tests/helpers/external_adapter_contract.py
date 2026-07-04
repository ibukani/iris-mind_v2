"""External adapter Runtime API contract fixtures.

この helper は Discord 専用ではなく、任意 provider の adapter が
ExternalAccountRef / ExternalSpaceRef 経由で Runtime API を使う形を固定する。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from iris.adapters.grpc.mappers import timestamp_from_datetime
from iris.contracts.actions import SendMessageAction
from iris.contracts.delivery import DeliveryEnvelope, DeliveryStatus, DeliveryTarget
from iris.core.ids import ActionId, CorrelationId, DeliveryId, ExternalRef, SessionId
from iris.generated.iris.api.v1 import identity_pb2, observations_pb2, spaces_pb2
from iris.generated.iris.runtime.v1 import runtime_pb2

CONTRACT_OCCURRED_AT = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)


@dataclass(frozen=True, kw_only=True)
class ExternalAdapterContractFixture:
    """Provider-neutral external adapter fixture.

    Discord voice is only one fixture instance.  Tests using this type should keep
    provider, account, and space values replaceable for future Slack/Web/Avatar adapters.
    """

    name: str
    provider: str
    source: str
    provider_subject: str
    account_display_name: str
    provider_space_ref: str
    space_display_name: str
    space_kind: spaces_pb2.SpaceKind.ValueType
    session_id: str
    actor_message_text: str
    activity_kind: observations_pb2.ActivityKind.ValueType


def generic_text_adapter_fixture() -> ExternalAdapterContractFixture:
    """Return a generic non-Discord external adapter fixture.

    Returns:
        Provider-neutral text adapter fixture.
    """
    return ExternalAdapterContractFixture(
        name="generic_text",
        provider="generic-chat",
        source="generic-chat",
        provider_subject="generic-user-1",
        account_display_name="Generic User",
        provider_space_ref="generic-room-1",
        space_display_name="Generic Room",
        space_kind=spaces_pb2.SPACE_KIND_ROOM,
        session_id="generic-session-1",
        actor_message_text="hello from a generic adapter",
        activity_kind=observations_pb2.ACTIVITY_KIND_SYSTEM_INTERACTION,
    )


def discord_voice_adapter_fixture() -> ExternalAdapterContractFixture:
    """Return a Discord voice-shaped fixture as one generic adapter case.

    Returns:
        Discord voice adapter fixture.
    """
    return ExternalAdapterContractFixture(
        name="discord_voice",
        provider="discord",
        source="discord",
        provider_subject="discord-user-1",
        account_display_name="Discord User",
        provider_space_ref="discord-voice-channel-1",
        space_display_name="Voice Lounge",
        space_kind=spaces_pb2.SPACE_KIND_VOICE_CHANNEL,
        session_id="discord-voice-session-1",
        actor_message_text="voice transcript hello",
        activity_kind=observations_pb2.ACTIVITY_KIND_VOICE_JOINED,
    )


def external_adapter_contract_fixtures() -> tuple[ExternalAdapterContractFixture, ...]:
    """Return all reusable external adapter fixtures.

    Returns:
        Generic and representative Discord fixtures.
    """
    return (
        generic_text_adapter_fixture(),
        discord_voice_adapter_fixture(),
    )


def build_actor_message_request(
    fixture: ExternalAdapterContractFixture,
    *,
    correlation_id: str = "contract-corr-1",
    observation_id: str = "contract-obs-1",
    text: str | None = None,
) -> runtime_pb2.SubmitObservationRequest:
    """Build an actor_message SubmitObservation request using external refs.

    Returns:
        SubmitObservationRequest for actor_message.
    """
    return _build_submit_observation_request(
        fixture,
        correlation_id=correlation_id,
        observation_id=observation_id,
        kind=observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE,
        payload=observations_pb2.ActorMessagePayload(
            text=text or fixture.actor_message_text,
            external_message_id=f"msg-{observation_id}",
        ),
    )


def build_activity_event_request(
    fixture: ExternalAdapterContractFixture,
    *,
    correlation_id: str = "activity-corr-1",
    observation_id: str = "activity-obs-1",
) -> runtime_pb2.SubmitObservationRequest:
    """Build an activity_event SubmitObservation request using external refs.

    Returns:
        SubmitObservationRequest for activity_event.
    """
    return _build_submit_observation_request(
        fixture,
        correlation_id=correlation_id,
        observation_id=observation_id,
        kind=observations_pb2.OBSERVATION_KIND_ACTIVITY_EVENT,
        payload=observations_pb2.ActivityEventPayload(
            activity_kind=fixture.activity_kind,
            provider_event_id=f"event-{observation_id}",
            provider_sequence=1,
            metadata={"fixture": fixture.name},
        ),
    )


def build_presence_signal_request(
    fixture: ExternalAdapterContractFixture,
    *,
    correlation_id: str = "presence-corr-1",
    observation_id: str = "presence-obs-1",
) -> runtime_pb2.SubmitObservationRequest:
    """Build a presence_signal SubmitObservation request using external refs.

    Returns:
        SubmitObservationRequest for presence_signal.
    """
    return _build_submit_observation_request(
        fixture,
        correlation_id=correlation_id,
        observation_id=observation_id,
        kind=observations_pb2.OBSERVATION_KIND_PRESENCE_SIGNAL,
        payload=observations_pb2.PresenceSignalPayload(
            status=observations_pb2.PRESENCE_STATUS_ONLINE,
            metadata={"fixture": fixture.name},
        ),
    )


def build_send_message_delivery(
    fixture: ExternalAdapterContractFixture,
    *,
    delivery_id: str = "contract-delivery-1",
    action_id: str = "contract-action-1",
    correlation_id: str = "contract-corr-1",
    text: str = "hello from runtime delivery",
) -> DeliveryEnvelope:
    """Build a due SendMessageAction delivery item for pull-based adapter delivery.

    Returns:
        Pending DeliveryEnvelope scoped to the fixture provider and target.
    """
    return DeliveryEnvelope(
        delivery_id=DeliveryId(delivery_id),
        action=SendMessageAction(
            action_id=ActionId(action_id),
            session_id=SessionId(fixture.session_id),
            correlation_id=CorrelationId(correlation_id),
            text=text,
        ),
        target=DeliveryTarget(
            provider=fixture.provider,
            provider_subject=ExternalRef(fixture.provider_subject),
            provider_space_ref=ExternalRef(fixture.provider_space_ref),
            session_id=SessionId(fixture.session_id),
        ),
        status=DeliveryStatus.PENDING,
        created_at=CONTRACT_OCCURRED_AT,
        updated_at=CONTRACT_OCCURRED_AT,
        not_before=None,
        attempts=0,
        max_attempts=3,
        idempotency_key=f"idem-{delivery_id}",
    )


def build_observation_context(
    fixture: ExternalAdapterContractFixture,
) -> observations_pb2.ObservationContext:
    """Build provider-consistent ObservationContext with external refs.

    Returns:
        ObservationContext containing ExternalAccountRef and ExternalSpaceRef.
    """
    return observations_pb2.ObservationContext(
        source=fixture.source,
        account_ref=identity_pb2.ExternalAccountRef(
            provider=fixture.provider,
            provider_subject=fixture.provider_subject,
            display_name=fixture.account_display_name,
            actor_kind=identity_pb2.ACTOR_KIND_HUMAN,
            metadata={"fixture": fixture.name},
        ),
        space_ref=spaces_pb2.ExternalSpaceRef(
            provider=fixture.provider,
            provider_space_ref=fixture.provider_space_ref,
            display_name=fixture.space_display_name,
            space_kind=fixture.space_kind,
            metadata={"fixture": fixture.name},
        ),
    )


type _ObservationPayload = (
    observations_pb2.ActorMessagePayload
    | observations_pb2.ActivityEventPayload
    | observations_pb2.PresenceSignalPayload
)


def _build_submit_observation_request(
    fixture: ExternalAdapterContractFixture,
    *,
    correlation_id: str,
    observation_id: str,
    kind: observations_pb2.ObservationKind.ValueType,
    payload: _ObservationPayload,
) -> runtime_pb2.SubmitObservationRequest:
    observation = observations_pb2.Observation(
        observation_id=observation_id,
        session_id=fixture.session_id,
        kind=kind,
        occurred_at=timestamp_from_datetime(CONTRACT_OCCURRED_AT),
        context=build_observation_context(fixture),
    )
    _copy_payload(observation, payload)
    return runtime_pb2.SubmitObservationRequest(
        correlation_id=correlation_id,
        observation=observation,
    )


def _copy_payload(
    observation: observations_pb2.Observation,
    payload: _ObservationPayload,
) -> None:
    if isinstance(payload, observations_pb2.ActorMessagePayload):
        observation.actor_message.CopyFrom(payload)
    elif isinstance(payload, observations_pb2.ActivityEventPayload):
        observation.activity_event.CopyFrom(payload)
    else:
        observation.presence_signal.CopyFrom(payload)
