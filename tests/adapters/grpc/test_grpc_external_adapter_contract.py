"""gRPC wire-level external adapter Runtime API contract tests."""

from __future__ import annotations

import json
import socket
from typing import TYPE_CHECKING

import grpc
import pytest

from iris.adapters.app_gateway.fake_resolvers import FakeIdentityResolver, FakeSpaceResolver
from iris.core.ids import DeliveryId
from iris.generated.iris.runtime.v1 import runtime_pb2, runtime_pb2_grpc
from iris.runtime.auth.static_tokens import StaticBearerTokenVerifier, hash_token
from iris.runtime.config.auth import RuntimeAuthConfig, RuntimeAuthMode
from iris.runtime.delivery.broker import RuntimeAppActionBroker
from iris.runtime.delivery.in_memory import InMemoryDeliveryOutbox
from iris.runtime.wiring.grpc import create_grpc_server
from tests.helpers.external_adapter_contract import (
    ExternalAdapterContractFixture,
    build_activity_event_request,
    build_actor_message_request,
    build_presence_signal_request,
    build_send_message_delivery,
    discord_voice_adapter_fixture,
    external_adapter_contract_fixtures,
    generic_text_adapter_fixture,
)
from tests.helpers.grpc_test import RecordingRuntimeService

if TYPE_CHECKING:
    from types import TracebackType

    from iris.adapters.app_gateway.ports import AppActionBroker

pytestmark = pytest.mark.anyio

_CREDENTIAL = "contract-adapter-sample"
_AUTH_METADATA = (("authorization", f"Bearer {_CREDENTIAL}"),)


@pytest.mark.parametrize(
    "fixture", external_adapter_contract_fixtures(), ids=lambda item: item.name
)
async def test_submit_observation_accepts_external_adapter_actor_message(
    fixture: ExternalAdapterContractFixture,
) -> None:
    """SubmitObservation accepts actor_message requests with external account/space refs."""
    service = RecordingRuntimeService("wire reply")
    async with _GrpcExternalAdapterHarness(fixture, runtime_service=service) as stub:
        response = await stub.SubmitObservation(
            build_actor_message_request(fixture),
            metadata=_AUTH_METADATA,
        )

    assert response.correlation_id == "contract-corr-1"
    assert response.output.text == "wire reply"
    assert service.envelope is not None
    assert service.envelope.observation.context.actor is not None
    assert service.envelope.observation.context.actor.provider == fixture.provider
    assert service.envelope.observation.context.space_id is not None


async def test_submit_observation_accepts_discord_voice_fixture_as_generic_case() -> None:
    """Discord voice adapter fixture is accepted through the same generic contract path."""
    fixture = discord_voice_adapter_fixture()
    service = RecordingRuntimeService("discord wire reply")
    async with _GrpcExternalAdapterHarness(fixture, runtime_service=service) as stub:
        response = await stub.SubmitObservation(
            build_actor_message_request(fixture),
            metadata=_AUTH_METADATA,
        )

    assert response.output.text == "discord wire reply"
    assert service.envelope is not None
    assert service.envelope.observation.context.actor is not None
    assert service.envelope.observation.context.actor.provider == "discord"


async def test_activity_event_wire_contract_accepts_external_refs() -> None:
    """ActivityEvent wire request accepts external account/space refs."""
    fixture = discord_voice_adapter_fixture()
    service = RecordingRuntimeService("accepted")
    async with _GrpcExternalAdapterHarness(fixture, runtime_service=service) as stub:
        response = await stub.SubmitObservation(
            build_activity_event_request(fixture),
            metadata=_AUTH_METADATA,
        )

    assert response.output.text == "accepted"
    assert service.envelope is not None
    assert service.envelope.observation.kind.value == "activity_event"


async def test_presence_signal_wire_contract_accepts_external_refs() -> None:
    """PresenceSignal wire request accepts external account/space refs."""
    fixture = generic_text_adapter_fixture()
    service = RecordingRuntimeService("accepted")
    async with _GrpcExternalAdapterHarness(fixture, runtime_service=service) as stub:
        response = await stub.SubmitObservation(
            build_presence_signal_request(fixture),
            metadata=_AUTH_METADATA,
        )

    assert response.output.text == "accepted"
    assert service.envelope is not None
    assert service.envelope.observation.kind.value == "presence_signal"


async def test_submit_observation_rejects_external_client_internal_actor_claim() -> None:
    """External clients must not send internal Identity actor claims."""
    fixture = generic_text_adapter_fixture()
    request = build_actor_message_request(fixture)
    request.observation.context.actor.actor_id = "spoofed-actor"

    async with _GrpcExternalAdapterHarness(fixture) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await stub.SubmitObservation(request, metadata=_AUTH_METADATA)

    assert exc_info.value.code() is grpc.StatusCode.PERMISSION_DENIED


async def test_submit_observation_rejects_external_client_internal_account_id() -> None:
    """External clients must not send internal account_id claims."""
    fixture = generic_text_adapter_fixture()
    request = build_actor_message_request(fixture)
    request.observation.context.account_id = "spoofed-account"

    async with _GrpcExternalAdapterHarness(fixture) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await stub.SubmitObservation(request, metadata=_AUTH_METADATA)

    assert exc_info.value.code() is grpc.StatusCode.PERMISSION_DENIED


async def test_submit_observation_rejects_external_client_internal_space_id() -> None:
    """External clients must not send internal space_id claims."""
    fixture = generic_text_adapter_fixture()
    request = build_actor_message_request(fixture)
    request.observation.context.space_id = "spoofed-space"

    async with _GrpcExternalAdapterHarness(fixture) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await stub.SubmitObservation(request, metadata=_AUTH_METADATA)

    assert exc_info.value.code() is grpc.StatusCode.PERMISSION_DENIED


async def test_submit_observation_rejects_mismatched_account_and_space_provider() -> None:
    """Account and space refs must stay provider-consistent."""
    fixture = generic_text_adapter_fixture()
    request = build_actor_message_request(fixture)
    request.observation.context.space_ref.provider = "other-provider"

    async with _GrpcExternalAdapterHarness(
        fixture,
        allowed_providers=(fixture.provider, "other-provider"),
    ) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await stub.SubmitObservation(request, metadata=_AUTH_METADATA)

    assert exc_info.value.code() is grpc.StatusCode.PERMISSION_DENIED


async def test_poll_app_actions_wire_contract_returns_provider_scoped_send_message() -> None:
    """PollAppActions leases only due actions for the requested provider."""
    fixture = generic_text_adapter_fixture()
    outbox = InMemoryDeliveryOutbox()
    await outbox.enqueue(build_send_message_delivery(fixture))
    await outbox.enqueue(
        build_send_message_delivery(
            discord_voice_adapter_fixture(),
            delivery_id="discord-delivery-1",
            action_id="discord-action-1",
            correlation_id="discord-corr-1",
        )
    )
    broker = RuntimeAppActionBroker(outbox=outbox, lease_seconds=60.0)

    async with _GrpcExternalAdapterHarness(fixture, app_action_broker=broker) as stub:
        response = await stub.PollAppActions(
            runtime_pb2.PollAppActionsRequest(provider=fixture.provider, max_items=10),
            metadata=_AUTH_METADATA,
        )

    assert len(response.actions) == 1
    action = response.actions[0]
    assert action.provider == fixture.provider
    assert action.provider_subject == fixture.provider_subject
    assert action.provider_space_ref == fixture.provider_space_ref
    assert action.send_message.text == "hello from runtime delivery"
    assert action.delivery_id == "contract-delivery-1"
    assert action.lease_id


async def test_report_action_result_wire_contract_accepts_succeeded() -> None:
    """ReportActionResult accepts a succeeded report for a leased action."""
    fixture = generic_text_adapter_fixture()
    outbox = InMemoryDeliveryOutbox()
    await outbox.enqueue(build_send_message_delivery(fixture))
    broker = RuntimeAppActionBroker(outbox=outbox, lease_seconds=60.0)

    async with _GrpcExternalAdapterHarness(fixture, app_action_broker=broker) as stub:
        poll = await stub.PollAppActions(
            runtime_pb2.PollAppActionsRequest(provider=fixture.provider, max_items=1),
            metadata=_AUTH_METADATA,
        )
        action = poll.actions[0]
        response = await stub.ReportActionResult(
            runtime_pb2.ReportActionResultRequest(
                delivery_id=action.delivery_id,
                lease_id=action.lease_id,
                action_id=action.action_id,
                correlation_id=action.correlation_id,
                status="succeeded",
                external_message_id="provider-message-1",
            ),
            metadata=_AUTH_METADATA,
        )
        repeated_poll = await stub.PollAppActions(
            runtime_pb2.PollAppActionsRequest(provider=fixture.provider, max_items=1),
            metadata=_AUTH_METADATA,
        )

    assert response == runtime_pb2.ReportActionResultResponse()
    assert repeated_poll.actions == []


async def test_report_action_result_rejects_wrong_provider_principal() -> None:
    """ReportActionResult is denied when token is not allowed for the delivery provider."""
    fixture = generic_text_adapter_fixture()
    outbox = InMemoryDeliveryOutbox()
    await outbox.enqueue(build_send_message_delivery(fixture))
    broker = RuntimeAppActionBroker(outbox=outbox, lease_seconds=60.0)

    async with _GrpcExternalAdapterHarness(
        fixture,
        app_action_broker=broker,
        allowed_providers=("other-provider",),
    ) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await stub.ReportActionResult(
                runtime_pb2.ReportActionResultRequest(
                    delivery_id="contract-delivery-1",
                    lease_id="lease-1",
                    action_id="contract-action-1",
                    correlation_id="contract-corr-1",
                    status="succeeded",
                ),
                metadata=_AUTH_METADATA,
            )

    assert exc_info.value.code() is grpc.StatusCode.PERMISSION_DENIED
    assert await broker.get_delivery_provider(DeliveryId("contract-delivery-1")) == fixture.provider


class _GrpcExternalAdapterHarness:
    """In-process gRPC server for external adapter contract tests."""

    def __init__(
        self,
        fixture: ExternalAdapterContractFixture,
        *,
        runtime_service: RecordingRuntimeService | None = None,
        app_action_broker: AppActionBroker | None = None,
        allowed_providers: tuple[str, ...] | None = None,
    ) -> None:
        self._fixture = fixture
        self._runtime_service = runtime_service or RecordingRuntimeService("unused")
        self._app_action_broker = app_action_broker
        self._allowed_providers = allowed_providers or (fixture.provider,)
        self._server: grpc.aio.Server | None = None
        self._channel: grpc.aio.Channel | None = None

    async def __aenter__(self) -> runtime_pb2_grpc.IrisRuntimeServiceAsyncStub:
        """Start the in-process server.

        Returns:
            Connected async runtime service stub.
        """
        port = _free_tcp_port()
        server = create_grpc_server(
            self._runtime_service,
            port=port,
            auth_config=RuntimeAuthConfig(
                mode=RuntimeAuthMode.REQUIRED,
                allow_insecure_remote=True,
            ),
            token_verifier=_token_verifier(
                fixture=self._fixture,
                allowed_providers=self._allowed_providers,
            ),
            identity_resolver=FakeIdentityResolver(),
            space_resolver=FakeSpaceResolver(),
            app_action_broker=self._app_action_broker,
        )
        self._server = server
        await server.start()
        self._channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
        await self._channel.channel_ready()
        return runtime_pb2_grpc.IrisRuntimeServiceStub(self._channel)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close channel and stop the in-process server."""
        del exc_type, exc, traceback
        if self._channel is not None:
            await self._channel.close()
        if self._server is not None:
            await self._server.stop(grace=None)


def _token_verifier(
    *,
    fixture: ExternalAdapterContractFixture,
    allowed_providers: tuple[str, ...],
) -> StaticBearerTokenVerifier:
    token_entries = [
        {
            "client_id": f"{fixture.provider}-adapter",
            "token_sha256": hash_token(_CREDENTIAL),
            "client_kind": "external_client",
            "provider": fixture.provider,
            "allowed_providers": list(allowed_providers),
            "scopes": [
                "observation.submit",
                "delivery.poll",
                "delivery.report",
            ],
            "observation_capabilities": [],
        }
    ]
    return StaticBearerTokenVerifier.from_env({"TOKENS": json.dumps(token_entries)}, "TOKENS")


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
