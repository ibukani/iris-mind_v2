"""Tests for gRPC runtime DTO mappers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, override

import pytest

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.contracts.external_refs import ExternalAccountRef, ExternalSpaceRef

from iris.adapters.app_gateway.fake_resolvers import FakeIdentityResolver
from iris.adapters.app_gateway.ports import IdentityResolver, SpaceResolver
from iris.adapters.grpc.mappers import (
    GrpcMappingError,
    GrpcRuntimeMapper,
    identity_from_proto,
    runtime_response_to_proto,
    timestamp_from_datetime,
)
from iris.contracts.actions import PresentedOutput
from iris.contracts.activity import ActivityKind
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActivityEventObservation,
    ActorMessageObservation,
    IdleTickObservation,
    PresenceSignalObservation,
)
from iris.contracts.presence import PresenceStatus
from iris.contracts.spaces import InteractionSpace, SpaceKind
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
from iris.generated.iris.runtime.v1 import runtime_pb2
from iris.runtime.service import RuntimeResponse
from tests.helpers.approx import approx

if TYPE_CHECKING:
    from collections.abc import Mapping

_OCCURRED_AT = datetime(2026, 6, 5, 12, 30, tzinfo=UTC)


@pytest.mark.anyio
async def test_actor_message_proto_maps_to_observation_envelope() -> None:
    """ActorMessage protoがObservationEnvelopeへmapされることを確認する。"""
    request = runtime_pb2.SubmitObservationRequest(
        correlation_id="corr-1",
        observation=_actor_message_proto(),
    )

    envelope = await _mapper().observation_envelope_from_proto(request)

    assert envelope.correlation_id == CorrelationId("corr-1")
    assert isinstance(envelope.observation, ActorMessageObservation)
    assert envelope.observation.observation_id == ObservationId("obs-1")
    assert envelope.observation.session_id == SessionId("session-1")
    assert envelope.observation.occurred_at == _OCCURRED_AT
    assert envelope.observation.text == "hello grpc"
    assert envelope.observation.external_message_id == ExternalRef("message-1")


@pytest.mark.anyio
async def test_idle_tick_proto_maps_to_observation() -> None:
    """IdleTick protoがIdleTickObservationへmapされることを確認する。"""
    observation = await _mapper().observation_from_proto(
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


@pytest.mark.anyio
async def test_activity_event_proto_maps_to_observation() -> None:
    """ActivityEvent protoがtyped ActivityEventObservationへmapされることを確認する。"""
    observation = await _mapper().observation_from_proto(
        observations_pb2.Observation(
            observation_id="obs-activity",
            session_id="session-1",
            kind=observations_pb2.OBSERVATION_KIND_ACTIVITY_EVENT,
            occurred_at=timestamp_from_datetime(_OCCURRED_AT),
            activity_event=observations_pb2.ActivityEventPayload(
                activity_kind=observations_pb2.ACTIVITY_KIND_VOICE_JOINED,
                provider_event_id="event-1",
                provider_sequence=42,
                metadata={"discord_guild_id": "guild-1"},
            ),
        )
    )

    assert isinstance(observation, ActivityEventObservation)
    assert observation.activity_kind is ActivityKind.VOICE_JOINED
    assert observation.provider_event_id == "event-1"
    assert observation.provider_sequence == 42
    assert observation.metadata == {"discord_guild_id": "guild-1"}


@pytest.mark.anyio
async def test_activity_event_zero_sequence_maps_to_none() -> None:
    """provider_sequence=0が未指定を表すNoneへmapされることを確認する。"""
    observation = await _mapper().observation_from_proto(
        observations_pb2.Observation(
            observation_id="obs-activity",
            session_id="session-1",
            kind=observations_pb2.OBSERVATION_KIND_ACTIVITY_EVENT,
            occurred_at=timestamp_from_datetime(_OCCURRED_AT),
            activity_event=observations_pb2.ActivityEventPayload(
                activity_kind=observations_pb2.ACTIVITY_KIND_APP_OPENED,
            ),
        )
    )

    assert isinstance(observation, ActivityEventObservation)
    assert observation.provider_event_id is None
    assert observation.provider_sequence is None


@pytest.mark.anyio
async def test_activity_event_core_fields_are_not_read_from_metadata() -> None:
    """Activityの中核意味がmetadataの競合値で上書きされないことを確認する。"""
    observation = await _mapper().observation_from_proto(
        observations_pb2.Observation(
            observation_id="obs-activity",
            session_id="session-1",
            kind=observations_pb2.OBSERVATION_KIND_ACTIVITY_EVENT,
            occurred_at=timestamp_from_datetime(_OCCURRED_AT),
            activity_event=observations_pb2.ActivityEventPayload(
                activity_kind=observations_pb2.ACTIVITY_KIND_APP_OPENED,
                provider_event_id="typed-event",
                provider_sequence=7,
                metadata={
                    "activity_kind": "voice_left",
                    "provider_event_id": "metadata-event",
                    "provider_sequence": "99",
                },
            ),
        )
    )

    assert isinstance(observation, ActivityEventObservation)
    assert observation.activity_kind is ActivityKind.APP_OPENED
    assert observation.provider_event_id == "typed-event"
    assert observation.provider_sequence == 7


@pytest.mark.anyio
async def test_presence_signal_proto_maps_to_observation() -> None:
    """PresenceSignal protoがtyped PresenceSignalObservationへmapされることを確認する。"""
    expires_at = datetime(2026, 6, 5, 13, tzinfo=UTC)
    observation = await _mapper().observation_from_proto(
        observations_pb2.Observation(
            observation_id="obs-presence",
            session_id="session-1",
            kind=observations_pb2.OBSERVATION_KIND_PRESENCE_SIGNAL,
            occurred_at=timestamp_from_datetime(_OCCURRED_AT),
            presence_signal=observations_pb2.PresenceSignalPayload(
                status=observations_pb2.PRESENCE_STATUS_DO_NOT_DISTURB,
                expires_at=timestamp_from_datetime(expires_at),
                metadata={"client_name": "desktop"},
            ),
        )
    )

    assert isinstance(observation, PresenceSignalObservation)
    assert observation.status is PresenceStatus.DO_NOT_DISTURB
    assert observation.expires_at == expires_at
    assert observation.metadata == {"client_name": "desktop"}


@pytest.mark.anyio
async def test_presence_signal_core_fields_are_not_read_from_metadata() -> None:
    """Presenceの中核意味がmetadataの競合値で上書きされないことを確認する。"""
    expires_at = datetime(2026, 6, 5, 13, tzinfo=UTC)
    observation = await _mapper().observation_from_proto(
        observations_pb2.Observation(
            observation_id="obs-presence",
            session_id="session-1",
            kind=observations_pb2.OBSERVATION_KIND_PRESENCE_SIGNAL,
            occurred_at=timestamp_from_datetime(_OCCURRED_AT),
            presence_signal=observations_pb2.PresenceSignalPayload(
                status=observations_pb2.PRESENCE_STATUS_AWAY,
                expires_at=timestamp_from_datetime(expires_at),
                metadata={
                    "presence_status": "offline",
                    "expires_at": "2099-01-01T00:00:00Z",
                },
            ),
        )
    )

    assert isinstance(observation, PresenceSignalObservation)
    assert observation.status is PresenceStatus.AWAY
    assert observation.expires_at == expires_at


@pytest.mark.anyio
async def test_presence_signal_without_expiry_maps_to_none() -> None:
    """expires_at未指定のpresence updateがNoneを保持することを確認する。"""
    observation = await _mapper().observation_from_proto(
        observations_pb2.Observation(
            observation_id="obs-presence",
            session_id="session-1",
            kind=observations_pb2.OBSERVATION_KIND_PRESENCE_SIGNAL,
            occurred_at=timestamp_from_datetime(_OCCURRED_AT),
            presence_signal=observations_pb2.PresenceSignalPayload(
                status=observations_pb2.PRESENCE_STATUS_ONLINE,
            ),
        )
    )

    assert isinstance(observation, PresenceSignalObservation)
    assert observation.expires_at is None


@pytest.mark.anyio
async def test_observation_context_actor_maps_to_identity() -> None:
    """ObservationContext actor protoがIdentityへmapされることを確認する。"""
    observation = await _mapper().observation_from_proto(_actor_message_proto())

    assert isinstance(observation, ActorMessageObservation)
    actor = observation.context.actor
    assert actor is not None
    assert actor.actor_id == ActorId("actor-1")
    assert actor.actor_kind == ActorKind.HUMAN
    assert actor.display_name == "Mina"
    assert actor.provider == "test"
    assert actor.provider_subject == ExternalRef("provider-actor-1")
    assert actor.account_id == AccountId("account-1")
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


@pytest.mark.anyio
async def test_invalid_observation_kind_raises_mapping_error() -> None:
    """Unsupported/unspecified kindがGrpcMappingErrorになることを確認する。"""
    request = _actor_message_proto()
    request.kind = observations_pb2.OBSERVATION_KIND_UNSPECIFIED

    with pytest.raises(GrpcMappingError, match="unsupported or unspecified observation kind"):
        await _mapper().observation_from_proto(request)


@pytest.mark.anyio
async def test_actor_message_kind_without_payload_raises_mapping_error() -> None:
    """actor_message kindでpayloadがない場合にmapping errorになることを確認する。"""
    request = observations_pb2.Observation(
        observation_id="obs-1",
        session_id="session-1",
        kind=observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE,
        occurred_at=timestamp_from_datetime(_OCCURRED_AT),
    )

    with pytest.raises(GrpcMappingError, match="requires actor_message payload"):
        await _mapper().observation_from_proto(request)


@pytest.mark.anyio
async def test_idle_tick_kind_without_payload_raises_mapping_error() -> None:
    """idle_tick kindでpayloadがない場合にmapping errorになることを確認する。"""
    request = observations_pb2.Observation(
        observation_id="obs-1",
        session_id="session-1",
        kind=observations_pb2.OBSERVATION_KIND_IDLE_TICK,
        occurred_at=timestamp_from_datetime(_OCCURRED_AT),
    )

    with pytest.raises(GrpcMappingError, match="requires idle_tick payload"):
        await _mapper().observation_from_proto(request)


@pytest.mark.anyio
async def test_activity_event_kind_with_presence_payload_raises_mapping_error() -> None:
    """ACTIVITY_EVENT kindとpresence payloadの不一致が拒否されることを確認する。"""
    request = observations_pb2.Observation(
        observation_id="obs-1",
        session_id="session-1",
        kind=observations_pb2.OBSERVATION_KIND_ACTIVITY_EVENT,
        occurred_at=timestamp_from_datetime(_OCCURRED_AT),
        presence_signal=observations_pb2.PresenceSignalPayload(
            status=observations_pb2.PRESENCE_STATUS_ONLINE,
        ),
    )

    with pytest.raises(GrpcMappingError, match="requires activity_event payload"):
        await _mapper().observation_from_proto(request)


@pytest.mark.anyio
async def test_presence_signal_kind_with_activity_payload_raises_mapping_error() -> None:
    """PRESENCE_SIGNAL kindとactivity payloadの不一致が拒否されることを確認する。"""
    request = observations_pb2.Observation(
        observation_id="obs-1",
        session_id="session-1",
        kind=observations_pb2.OBSERVATION_KIND_PRESENCE_SIGNAL,
        occurred_at=timestamp_from_datetime(_OCCURRED_AT),
        activity_event=observations_pb2.ActivityEventPayload(
            activity_kind=observations_pb2.ACTIVITY_KIND_APP_CLOSED,
        ),
    )

    with pytest.raises(GrpcMappingError, match="requires presence_signal payload"):
        await _mapper().observation_from_proto(request)


@pytest.mark.anyio
async def test_unspecified_activity_kind_raises_mapping_error() -> None:
    """ACTIVITY_KIND_UNSPECIFIEDが拒否されることを確認する。"""
    request = observations_pb2.Observation(
        observation_id="obs-1",
        session_id="session-1",
        kind=observations_pb2.OBSERVATION_KIND_ACTIVITY_EVENT,
        occurred_at=timestamp_from_datetime(_OCCURRED_AT),
        activity_event=observations_pb2.ActivityEventPayload(
            activity_kind=observations_pb2.ACTIVITY_KIND_UNSPECIFIED,
        ),
    )

    with pytest.raises(GrpcMappingError, match="unsupported or unspecified activity kind"):
        await _mapper().observation_from_proto(request)


@pytest.mark.anyio
async def test_unspecified_presence_status_raises_mapping_error() -> None:
    """PRESENCE_STATUS_UNSPECIFIEDが拒否されることを確認する。"""
    request = observations_pb2.Observation(
        observation_id="obs-1",
        session_id="session-1",
        kind=observations_pb2.OBSERVATION_KIND_PRESENCE_SIGNAL,
        occurred_at=timestamp_from_datetime(_OCCURRED_AT),
        presence_signal=observations_pb2.PresenceSignalPayload(
            status=observations_pb2.PRESENCE_STATUS_UNSPECIFIED,
        ),
    )

    with pytest.raises(GrpcMappingError, match="unsupported or unspecified presence status"):
        await _mapper().observation_from_proto(request)


@pytest.mark.anyio
async def test_negative_activity_provider_sequence_raises_mapping_error() -> None:
    """負のprovider_sequenceが拒否されることを確認する。"""
    request = observations_pb2.Observation(
        observation_id="obs-1",
        session_id="session-1",
        kind=observations_pb2.OBSERVATION_KIND_ACTIVITY_EVENT,
        occurred_at=timestamp_from_datetime(_OCCURRED_AT),
        activity_event=observations_pb2.ActivityEventPayload(
            activity_kind=observations_pb2.ACTIVITY_KIND_SYSTEM_INTERACTION,
            provider_sequence=-1,
        ),
    )

    with pytest.raises(GrpcMappingError, match="provider_sequence must not be negative"):
        await _mapper().observation_from_proto(request)


@pytest.mark.anyio
async def test_account_ref_maps_to_resolved_identity() -> None:
    """account_refがIdentityResolverで解決されIdentityになることを確認する。"""
    resolver = _RecordingIdentityResolver()
    request = _actor_message_request_with_account_ref(
        provider="discord",
        provider_subject="12345",
        display_name="Mina",
    )

    envelope = await GrpcRuntimeMapper(identity_resolver=resolver).observation_envelope_from_proto(
        request
    )

    assert isinstance(envelope.observation, ActorMessageObservation)
    actor = envelope.observation.context.actor
    assert actor is not None
    assert actor.provider == "discord"
    assert actor.provider_subject == ExternalRef("12345")
    assert actor.display_name == "Mina"
    assert resolver.calls == 1


@pytest.mark.anyio
async def test_account_ref_passes_context_device_to_resolver() -> None:
    """account_ref解決時にcontextのdevice_idがresolverへ渡されることを確認する。"""
    resolver = _RecordingIdentityResolver()
    context = observations_pb2.ObservationContext(
        account_ref=identity_pb2.ExternalAccountRef(
            provider="discord",
            provider_subject="12345",
            display_name="Mina",
        ),
        device_id="device-1",
    )

    await GrpcRuntimeMapper(identity_resolver=resolver).observation_context_from_proto(context)

    assert resolver.device_id == DeviceId("device-1")


@pytest.mark.anyio
async def test_account_ref_passes_metadata_to_resolver() -> None:
    """account_ref metadataがresolverへ渡されることを確認する。"""
    resolver = _RecordingIdentityResolver()
    context = observations_pb2.ObservationContext(
        account_ref=identity_pb2.ExternalAccountRef(
            provider="discord",
            provider_subject="12345",
            display_name="Mina",
            metadata={"role": "tester", "lang": "ja"},
        ),
    )

    await GrpcRuntimeMapper(identity_resolver=resolver).observation_context_from_proto(context)

    assert resolver.metadata == {"role": "tester", "lang": "ja"}


@pytest.mark.anyio
async def test_account_ref_without_resolver_raises_mapping_error() -> None:
    """account_refがあるがresolverが未設定の場合にGrpcMappingErrorになることを確認する。"""
    context = observations_pb2.ObservationContext(
        account_ref=identity_pb2.ExternalAccountRef(
            provider="discord",
            provider_subject="12345",
            display_name="Mina",
        ),
    )

    with pytest.raises(GrpcMappingError, match="identity resolver is required for account_ref"):
        await GrpcRuntimeMapper().observation_context_from_proto(context)


@pytest.mark.anyio
async def test_actor_and_account_ref_together_raises_mapping_error() -> None:
    """actorとaccount_refの両方が設定された場合にGrpcMappingErrorになることを確認する。"""
    context = observations_pb2.ObservationContext(
        actor=identity_pb2.Identity(
            actor_id="actor-1",
            actor_kind=identity_pb2.ACTOR_KIND_HUMAN,
            display_name="Mina",
            provider="test",
            provider_subject="provider-actor-1",
        ),
        account_ref=identity_pb2.ExternalAccountRef(
            provider="discord",
            provider_subject="12345",
            display_name="Mina",
        ),
    )

    with pytest.raises(GrpcMappingError, match="must not include both actor and account_ref"):
        await _mapper_with_resolver().observation_context_from_proto(context)


@pytest.mark.anyio
async def test_account_ref_and_account_id_together_raises_mapping_error() -> None:
    """account_refとaccount_idの両方が設定された場合にGrpcMappingErrorになることを確認する。"""
    context = observations_pb2.ObservationContext(
        account_ref=identity_pb2.ExternalAccountRef(
            provider="discord",
            provider_subject="12345",
            display_name="Mina",
        ),
        account_id="account-1",
    )

    with pytest.raises(GrpcMappingError, match="must not include both account_ref and account_id"):
        await _mapper_with_resolver().observation_context_from_proto(context)


@pytest.mark.anyio
async def test_account_ref_without_provider_raises_mapping_error() -> None:
    """account_ref.providerが空の場合にGrpcMappingErrorになることを確認する。"""
    context = observations_pb2.ObservationContext(
        account_ref=identity_pb2.ExternalAccountRef(
            provider="",
            provider_subject="12345",
            display_name="Mina",
        ),
    )

    with pytest.raises(GrpcMappingError, match=r"account_ref\.provider is required"):
        await _mapper_with_resolver().observation_context_from_proto(context)


@pytest.mark.anyio
async def test_account_ref_without_provider_subject_raises_mapping_error() -> None:
    """account_ref.provider_subjectが空の場合にGrpcMappingErrorになることを確認する。"""
    context = observations_pb2.ObservationContext(
        account_ref=identity_pb2.ExternalAccountRef(
            provider="discord",
            provider_subject="",
            display_name="Mina",
        ),
    )

    with pytest.raises(GrpcMappingError, match=r"account_ref\.provider_subject is required"):
        await _mapper_with_resolver().observation_context_from_proto(context)


@pytest.mark.anyio
async def test_account_ref_without_display_name_raises_mapping_error() -> None:
    """account_ref.display_nameが空の場合にGrpcMappingErrorになることを確認する。"""
    context = observations_pb2.ObservationContext(
        account_ref=identity_pb2.ExternalAccountRef(
            provider="discord",
            provider_subject="12345",
            display_name="",
        ),
    )

    with pytest.raises(GrpcMappingError, match=r"account_ref\.display_name is required"):
        await _mapper_with_resolver().observation_context_from_proto(context)


@pytest.mark.anyio
async def test_account_ref_unspecified_actor_kind_defaults_to_human() -> None:
    """account_ref.actor_kindがUNSPECIFIEDの場合にHUMANへdefaultされることを確認する。"""
    resolver = _RecordingIdentityResolver()
    context = observations_pb2.ObservationContext(
        account_ref=identity_pb2.ExternalAccountRef(
            provider="discord",
            provider_subject="12345",
            display_name="Mina",
            actor_kind=identity_pb2.ACTOR_KIND_UNSPECIFIED,
        ),
    )

    await GrpcRuntimeMapper(identity_resolver=resolver).observation_context_from_proto(context)

    assert resolver.actor_kind == ActorKind.HUMAN


@pytest.mark.anyio
async def test_account_ref_explicit_actor_kind_passes_to_resolver() -> None:
    """account_ref.actor_kindが明示された場合にresolverへ渡されることを確認する。"""
    resolver = _RecordingIdentityResolver()
    context = observations_pb2.ObservationContext(
        account_ref=identity_pb2.ExternalAccountRef(
            provider="discord",
            provider_subject="12345",
            display_name="Mina",
            actor_kind=identity_pb2.ACTOR_KIND_DEVICE,
        ),
    )

    await GrpcRuntimeMapper(identity_resolver=resolver).observation_context_from_proto(context)

    assert resolver.actor_kind == ActorKind.DEVICE


def test_direct_identity_unspecified_actor_kind_raises_mapping_error() -> None:
    """直接渡されたIdentityのactor_kindがUNSPECIFIEDの場合にGrpcMappingErrorになることを確認する。"""
    identity = identity_pb2.Identity(
        actor_id="actor-1",
        actor_kind=identity_pb2.ACTOR_KIND_UNSPECIFIED,
        display_name="Mina",
        provider="test",
        provider_subject="provider-actor-1",
    )

    with pytest.raises(GrpcMappingError, match="unsupported or unspecified actor kind"):
        identity_from_proto(identity)


@pytest.mark.anyio
async def test_direct_identity_with_mismatched_account_id_raises_mapping_error() -> None:
    """直接渡されたIdentityのaccount_idがcontext.account_idと異なる場合にGrpcMappingErrorになることを確認する。"""
    context = observations_pb2.ObservationContext(
        actor=identity_pb2.Identity(
            actor_id="actor-1",
            actor_kind=identity_pb2.ACTOR_KIND_HUMAN,
            display_name="Mina",
            provider="test",
            provider_subject="provider-actor-1",
            account_id="account-a",
        ),
        account_id="account-b",
    )

    with pytest.raises(
        GrpcMappingError,
        match=r"context\.account_id and actor\.account_id do not match",
    ):
        await _mapper().observation_context_from_proto(context)


@pytest.mark.anyio
async def test_envelope_without_observation_raises_mapping_error() -> None:
    """observationがないrequestがGrpcMappingErrorになることを確認する。"""
    request = runtime_pb2.SubmitObservationRequest(correlation_id="corr-1")

    with pytest.raises(GrpcMappingError, match="observation is required"):
        await _mapper().observation_envelope_from_proto(request)


def test_identity_without_actor_id_raises_mapping_error() -> None:
    """actor_idがないIdentityがGrpcMappingErrorになることを確認する。"""
    identity = identity_pb2.Identity(
        actor_kind=identity_pb2.ACTOR_KIND_HUMAN,
        display_name="Mina",
        provider="test",
        provider_subject="provider-actor-1",
    )

    with pytest.raises(GrpcMappingError, match=r"identity\.actor_id is required"):
        identity_from_proto(identity)


def test_identity_without_provider_subject_raises_mapping_error() -> None:
    """provider_subjectがないIdentityがGrpcMappingErrorになることを確認する。"""
    identity = identity_pb2.Identity(
        actor_id="actor-1",
        actor_kind=identity_pb2.ACTOR_KIND_HUMAN,
        display_name="Mina",
        provider="test",
    )

    with pytest.raises(GrpcMappingError, match=r"identity\.provider_subject is required"):
        identity_from_proto(identity)


@pytest.mark.anyio
async def test_observation_without_occurred_at_raises_mapping_error() -> None:
    """occurred_atがないObservationがGrpcMappingErrorになることを確認する。"""
    observation = observations_pb2.Observation(
        observation_id="obs-1",
        session_id="session-1",
        kind=observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE,
        actor_message=observations_pb2.ActorMessagePayload(text="hello"),
    )

    with pytest.raises(GrpcMappingError, match="occurred_at is required"):
        await _mapper().observation_from_proto(observation)


@pytest.mark.anyio
async def test_observation_with_invalid_occurred_at_raises_mapping_error() -> None:
    """不正なoccurred_atがGrpcMappingErrorになることを確認する。"""
    observation = observations_pb2.Observation(
        observation_id="obs-1",
        session_id="session-1",
        kind=observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE,
        actor_message=observations_pb2.ActorMessagePayload(text="hello"),
    )
    timestamp = timestamp_from_datetime(datetime(9999, 12, 31, 23, 59, 59, tzinfo=UTC))
    timestamp.seconds = (1 << 63) - 1
    timestamp.nanos = 0
    observation.occurred_at.CopyFrom(timestamp)

    with pytest.raises(GrpcMappingError, match="occurred_at is invalid"):
        await _mapper().observation_from_proto(observation)


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
                account_id="account-1",
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


def _actor_message_request_with_account_ref(
    *,
    provider: str,
    provider_subject: str,
    display_name: str,
) -> runtime_pb2.SubmitObservationRequest:
    """account_ref付きActorMessage SubmitObservationRequest fixtureを作る。

    Returns:
        runtime_pb2.SubmitObservationRequest: Actor message request DTO with account_ref.
    """
    return runtime_pb2.SubmitObservationRequest(
        correlation_id="corr-1",
        observation=observations_pb2.Observation(
            observation_id="obs-1",
            session_id="session-1",
            kind=observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE,
            occurred_at=timestamp_from_datetime(_OCCURRED_AT),
            context=observations_pb2.ObservationContext(
                account_ref=identity_pb2.ExternalAccountRef(
                    provider=provider,
                    provider_subject=provider_subject,
                    display_name=display_name,
                ),
            ),
            actor_message=observations_pb2.ActorMessagePayload(text="hello grpc"),
        ),
    )


def _mapper() -> GrpcRuntimeMapper:
    """ResolverなしのGrpcRuntimeMapper factory for tests。

    Returns:
        GrpcRuntimeMapper: Mapper without identity resolver.
    """
    return GrpcRuntimeMapper()


def _mapper_with_resolver() -> GrpcRuntimeMapper:
    """FakeIdentityResolver付きGrpcRuntimeMapper factory for tests。

    Returns:
        GrpcRuntimeMapper: Mapper with a deterministic fake resolver.
    """
    return GrpcRuntimeMapper(identity_resolver=FakeIdentityResolver())


class _RecordingIdentityResolver(IdentityResolver):
    """IdentityResolver that records every resolve_identity call and returns Identity."""

    def __init__(self) -> None:
        """Initialize recorder with empty call list and default fields."""
        self.calls = 0
        self.provider = ""
        self.provider_subject = ExternalRef("")
        self.display_name = ""
        self.actor_kind = ActorKind.HUMAN
        self.account_id: AccountId | None = None
        self.device_id: DeviceId | None = None
        self.metadata: Mapping[str, str] = {}

    @override
    async def resolve_identity(
        self,
        account_ref: ExternalAccountRef,
        *,
        device_id: DeviceId | None = None,
    ) -> Identity:
        """Record call and return deterministic Identity.

        Returns:
            Identity: Identity with provider-derived actor_id.
        """
        self.calls += 1
        self.provider = account_ref.provider
        self.provider_subject = account_ref.provider_subject
        self.display_name = account_ref.display_name
        self.actor_kind = account_ref.actor_kind
        self.account_id = account_ref.account_id
        self.device_id = device_id
        self.metadata = dict(account_ref.metadata)
        return Identity(
            actor_id=ActorId(f"resolved-{account_ref.provider}-{account_ref.provider_subject}"),
            actor_kind=account_ref.actor_kind,
            display_name=account_ref.display_name,
            provider=account_ref.provider,
            provider_subject=account_ref.provider_subject,
            account_id=account_ref.account_id,
            device_id=device_id,
            metadata=dict(account_ref.metadata),
        )


class _RecordingSpaceResolver(SpaceResolver):
    """SpaceResolver that records calls and returns deterministic InteractionSpace."""

    def __init__(self) -> None:
        self.calls = 0
        self.provider = ""
        self.provider_space_ref = ExternalRef("")
        self.display_name = ""
        self.space_kind = SpaceKind.TEXT_CHANNEL
        self.metadata: Mapping[str, str] = {}

    @override
    async def resolve_space(
        self,
        space_ref: ExternalSpaceRef,
    ) -> InteractionSpace:
        self.calls += 1
        self.provider = space_ref.provider
        self.provider_space_ref = space_ref.provider_space_ref
        self.display_name = space_ref.display_name
        self.space_kind = space_ref.space_kind
        self.metadata = dict(space_ref.metadata)
        return InteractionSpace(
            space_id=SpaceId(f"resolved-space-{space_ref.provider}-{space_ref.provider_space_ref}"),
            space_kind=space_ref.space_kind,
            display_name=space_ref.display_name,
            metadata=dict(space_ref.metadata),
        )


@pytest.mark.anyio
async def test_space_ref_resolves_to_space_id_through_resolver() -> None:
    """space_refがSpaceResolverで解決されspace_idになることを確認する。"""
    resolver = _RecordingSpaceResolver()
    context = observations_pb2.ObservationContext(
        space_ref=spaces_pb2.ExternalSpaceRef(
            provider="discord",
            provider_space_ref="chan-1",
            display_name="General",
            space_kind=spaces_pb2.SPACE_KIND_TEXT_CHANNEL,
        )
    )

    mapper = GrpcRuntimeMapper(space_resolver=resolver)
    result = await mapper.observation_context_from_proto(context)

    assert result.space_id == SpaceId("resolved-space-discord-chan-1")
    assert resolver.calls == 1


@pytest.mark.anyio
async def test_space_ref_passes_fields_to_resolver() -> None:
    """space_refの各フィールドが正しくresolverに渡されることを確認する。"""
    resolver = _RecordingSpaceResolver()
    context = observations_pb2.ObservationContext(
        space_ref=spaces_pb2.ExternalSpaceRef(
            provider="discord",
            provider_space_ref="chan-1",
            display_name="General",
            space_kind=spaces_pb2.SPACE_KIND_ROOM,
            metadata={"guild": "999"},
        )
    )

    await GrpcRuntimeMapper(space_resolver=resolver).observation_context_from_proto(context)

    assert resolver.provider == "discord"
    assert resolver.provider_space_ref == ExternalRef("chan-1")
    assert resolver.display_name == "General"
    assert resolver.space_kind == SpaceKind.ROOM
    assert resolver.metadata == {"guild": "999"}


@pytest.mark.anyio
async def test_account_and_space_resolution_remain_separate() -> None:
    """actor解決とspace解決がparticipant snapshotなしで独立することを確認する。"""
    id_resolver = _RecordingIdentityResolver()
    space_resolver = _RecordingSpaceResolver()
    context = observations_pb2.ObservationContext(
        account_ref=identity_pb2.ExternalAccountRef(
            provider="discord",
            provider_subject="user-1",
            display_name="User",
        ),
        space_ref=spaces_pb2.ExternalSpaceRef(
            provider="discord",
            provider_space_ref="chan-1",
            display_name="General",
            space_kind=spaces_pb2.SPACE_KIND_TEXT_CHANNEL,
        ),
    )

    await GrpcRuntimeMapper(
        identity_resolver=id_resolver,
        space_resolver=space_resolver,
    ).observation_context_from_proto(context)

    assert id_resolver.calls == 1
    assert space_resolver.calls == 1
    assert space_resolver.space_kind is SpaceKind.TEXT_CHANNEL


@pytest.mark.anyio
async def test_voice_channel_space_kind_maps_to_resolver() -> None:
    """VOICE_CHANNEL protoがSpaceKind.VOICE_CHANNELへmapされることを確認する。"""
    resolver = _RecordingSpaceResolver()
    context = observations_pb2.ObservationContext(
        space_ref=spaces_pb2.ExternalSpaceRef(
            provider="discord",
            provider_space_ref="voice-1",
            display_name="Lobby",
            space_kind=spaces_pb2.SPACE_KIND_VOICE_CHANNEL,
        )
    )

    await GrpcRuntimeMapper(space_resolver=resolver).observation_context_from_proto(context)

    assert resolver.space_kind is SpaceKind.VOICE_CHANNEL


@pytest.mark.anyio
async def test_space_ref_without_resolver_raises_mapping_error() -> None:
    """space_resolverなしでspace_refを指定するとGrpcMappingErrorになることを確認する。"""
    context = observations_pb2.ObservationContext(
        space_ref=spaces_pb2.ExternalSpaceRef(
            provider="discord",
            provider_space_ref="chan-1",
            display_name="General",
            space_kind=spaces_pb2.SPACE_KIND_TEXT_CHANNEL,
        )
    )

    with pytest.raises(GrpcMappingError, match="space resolver is required for space_ref"):
        await GrpcRuntimeMapper().observation_context_from_proto(context)


@pytest.mark.anyio
async def test_space_ref_and_space_id_together_raises_mapping_error() -> None:
    """space_refとspace_idを同時に指定するとGrpcMappingErrorになることを確認する。"""
    context = observations_pb2.ObservationContext(
        space_id="space-x",
        space_ref=spaces_pb2.ExternalSpaceRef(
            provider="discord",
            provider_space_ref="chan-1",
            display_name="General",
            space_kind=spaces_pb2.SPACE_KIND_TEXT_CHANNEL,
        ),
    )

    mapper = GrpcRuntimeMapper(space_resolver=_RecordingSpaceResolver())
    with pytest.raises(GrpcMappingError, match="must not include both space_ref and space_id"):
        await mapper.observation_context_from_proto(context)


@pytest.mark.anyio
async def test_space_ref_without_provider_raises_mapping_error() -> None:
    """providerのないspace_refはGrpcMappingErrorになることを確認する。"""
    context = observations_pb2.ObservationContext(
        space_ref=spaces_pb2.ExternalSpaceRef(
            provider_space_ref="chan-1",
            display_name="General",
            space_kind=spaces_pb2.SPACE_KIND_TEXT_CHANNEL,
        )
    )

    mapper = GrpcRuntimeMapper(space_resolver=_RecordingSpaceResolver())
    with pytest.raises(GrpcMappingError, match=r"space_ref\.provider is required"):
        await mapper.observation_context_from_proto(context)


@pytest.mark.anyio
async def test_space_ref_without_provider_space_ref_raises_mapping_error() -> None:
    """provider_space_refのないspace_refはGrpcMappingErrorになることを確認する。"""
    context = observations_pb2.ObservationContext(
        space_ref=spaces_pb2.ExternalSpaceRef(
            provider="discord",
            display_name="General",
            space_kind=spaces_pb2.SPACE_KIND_TEXT_CHANNEL,
        )
    )

    mapper = GrpcRuntimeMapper(space_resolver=_RecordingSpaceResolver())
    with pytest.raises(GrpcMappingError, match=r"space_ref\.provider_space_ref is required"):
        await mapper.observation_context_from_proto(context)


@pytest.mark.anyio
async def test_space_ref_without_display_name_raises_mapping_error() -> None:
    """display_nameのないspace_refはGrpcMappingErrorになることを確認する。"""
    context = observations_pb2.ObservationContext(
        space_ref=spaces_pb2.ExternalSpaceRef(
            provider="discord",
            provider_space_ref="chan-1",
            space_kind=spaces_pb2.SPACE_KIND_TEXT_CHANNEL,
        )
    )

    mapper = GrpcRuntimeMapper(space_resolver=_RecordingSpaceResolver())
    with pytest.raises(GrpcMappingError, match=r"space_ref\.display_name is required"):
        await mapper.observation_context_from_proto(context)


@pytest.mark.anyio
async def test_space_ref_unspecified_kind_raises_mapping_error() -> None:
    """space_kindがUNSPECIFIEDなspace_refはGrpcMappingErrorになることを確認する。"""
    context = observations_pb2.ObservationContext(
        space_ref=spaces_pb2.ExternalSpaceRef(
            provider="discord",
            provider_space_ref="chan-1",
            display_name="General",
            space_kind=spaces_pb2.SPACE_KIND_UNSPECIFIED,
        )
    )

    mapper = GrpcRuntimeMapper(space_resolver=_RecordingSpaceResolver())
    with pytest.raises(GrpcMappingError, match=r"space_ref\.space_kind must not be unspecified"):
        await mapper.observation_context_from_proto(context)


@pytest.mark.anyio
async def test_direct_space_id_mapping_works() -> None:
    """space_idのみ指定された場合、そのままSpaceIdとしてマップされることを確認する。"""
    context = observations_pb2.ObservationContext(
        space_id="space-x",
    )

    result = await GrpcRuntimeMapper().observation_context_from_proto(context)

    assert result.space_id == SpaceId("space-x")
