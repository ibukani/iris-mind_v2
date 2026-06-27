"""gRPC auth interceptor integration tests."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import socket
from typing import TYPE_CHECKING

import grpc
import pytest

from iris.adapters.grpc.mappers import timestamp_from_datetime
from iris.runtime.delivery.broker import RuntimeAppActionBroker
from iris.runtime.delivery.in_memory import InMemoryDeliveryOutbox
from tests.runtime.delivery.test_in_memory_delivery_outbox import envelope

if TYPE_CHECKING:
    from types import TracebackType

    from iris.adapters.app_gateway.ports import AppActionBroker
from iris.generated.iris.api.v1 import observations_pb2
from iris.generated.iris.runtime.v1 import runtime_pb2, runtime_pb2_grpc
from iris.runtime.auth.static_tokens import StaticBearerTokenVerifier, hash_token
from iris.runtime.config.auth import RuntimeAuthConfig, RuntimeAuthMode
from iris.runtime.wiring.grpc import create_grpc_server
from tests.helpers.grpc_test import RecordingRuntimeService


@pytest.mark.anyio
async def test_missing_token_in_required_mode_is_unauthenticated() -> None:
    """Required auth mode rejects missing bearer token."""
    async with _AuthGrpcHarness(_verifier(scopes=("observation.submit",))) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await stub.SubmitObservation(_request())

    assert exc_info.value.code() is grpc.StatusCode.UNAUTHENTICATED


@pytest.mark.anyio
async def test_valid_token_missing_scope_is_permission_denied() -> None:
    """Valid bearer token without SubmitObservation scope reaches authz denial."""
    async with _AuthGrpcHarness(_verifier(scopes=("runtime.info.read",))) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await stub.SubmitObservation(
                _request(),
                metadata=(("authorization", "Bearer token-1"),),
            )

    assert exc_info.value.code() is grpc.StatusCode.PERMISSION_DENIED


@pytest.mark.anyio
async def test_valid_submit_observation_external_token_succeeds() -> None:
    """Valid external token can submit external-client observation."""
    service = RecordingRuntimeService("ok")
    async with _AuthGrpcHarness(
        _verifier(scopes=("observation.submit",)),
        runtime_service=service,
    ) as stub:
        response = await stub.SubmitObservation(
            _request(),
            metadata=(("authorization", "Bearer token-1"),),
        )

    assert response.output.text == "ok"
    assert service.envelope is not None
    assert not service.envelope.ingress.authenticated


@pytest.mark.anyio
async def test_local_dev_invalid_authorization_is_unauthenticated() -> None:
    """local_dev mode rejects invalid bearer token."""
    port = _free_tcp_port()
    server = create_grpc_server(
        RecordingRuntimeService("unused"),
        port=port,
        auth_config=RuntimeAuthConfig(
            mode=RuntimeAuthMode.LOCAL_DEV,
            allow_unauthenticated_loopback=True,
        ),
        token_verifier=_verifier(scopes=()),
    )
    await server.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = runtime_pb2_grpc.IrisRuntimeServiceStub(channel)
            with pytest.raises(grpc.aio.AioRpcError) as exc_info:
                await stub.SubmitObservation(
                    _request(),
                    metadata=(("authorization", "Bearer invalid-token"),),
                )
            assert exc_info.value.code() is grpc.StatusCode.UNAUTHENTICATED
    finally:
        await server.stop(grace=None)


@pytest.mark.anyio
async def test_report_action_result_without_token_in_required_mode_is_unauthenticated() -> None:
    """ReportActionResult requires token in required mode."""
    outbox = InMemoryDeliveryOutbox()
    await outbox.enqueue(envelope(provider="cli"))
    broker = RuntimeAppActionBroker(outbox)
    async with _AuthGrpcHarness(
        _verifier(scopes=("delivery.report",)), app_action_broker=broker
    ) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await stub.ReportActionResult(_report_request())
    assert exc_info.value.code() is grpc.StatusCode.UNAUTHENTICATED


@pytest.mark.anyio
async def test_report_action_result_valid_token_missing_scope_is_permission_denied() -> None:
    """ReportActionResult requires delivery.report scope."""
    outbox = InMemoryDeliveryOutbox()
    await outbox.enqueue(envelope(provider="cli"))
    broker = RuntimeAppActionBroker(outbox)
    async with _AuthGrpcHarness(
        _verifier(scopes=("observation.submit",)), app_action_broker=broker
    ) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await stub.ReportActionResult(
                _report_request(), metadata=(("authorization", "Bearer token-1"),)
            )
    assert exc_info.value.code() is grpc.StatusCode.PERMISSION_DENIED


@pytest.mark.anyio
async def test_report_action_result_valid_token_wrong_provider_is_permission_denied() -> None:
    """ReportActionResult requires delivery provider match."""
    outbox = InMemoryDeliveryOutbox()
    await outbox.enqueue(envelope(provider="cli"))
    broker = RuntimeAppActionBroker(outbox)
    verifier = _verifier(scopes=("delivery.report",), allowed_providers=["slack"])
    async with _AuthGrpcHarness(verifier, app_action_broker=broker) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await stub.ReportActionResult(
                _report_request(), metadata=(("authorization", "Bearer token-1"),)
            )
    assert exc_info.value.code() is grpc.StatusCode.PERMISSION_DENIED


@pytest.mark.anyio
async def test_report_action_result_valid_token_matching_provider_succeeds() -> None:
    """ReportActionResult succeeds if scope and provider match."""
    outbox = InMemoryDeliveryOutbox()
    await outbox.enqueue(envelope(provider="cli"))
    broker = RuntimeAppActionBroker(outbox)
    # Report fails with FAILED_PRECONDITION (mismatched lease) but passes auth.
    async with _AuthGrpcHarness(
        _verifier(scopes=("delivery.report",)), app_action_broker=broker
    ) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await stub.ReportActionResult(
                _report_request(), metadata=(("authorization", "Bearer token-1"),)
            )
    assert exc_info.value.code() is grpc.StatusCode.FAILED_PRECONDITION


class _AuthGrpcHarness:
    """In-process gRPC server with required auth."""

    def __init__(
        self,
        verifier: StaticBearerTokenVerifier,
        *,
        runtime_service: RecordingRuntimeService | None = None,
        app_action_broker: AppActionBroker | None = None,
    ) -> None:
        self._verifier = verifier
        self._runtime_service = runtime_service or RecordingRuntimeService("unused")
        self._app_action_broker = app_action_broker
        self._server: grpc.aio.Server | None = None
        self._channel: grpc.aio.Channel | None = None

    async def __aenter__(self) -> runtime_pb2_grpc.IrisRuntimeServiceAsyncStub:
        port = _free_tcp_port()
        server = create_grpc_server(
            self._runtime_service,
            port=port,
            auth_config=RuntimeAuthConfig(
                mode=RuntimeAuthMode.REQUIRED,
                allow_insecure_remote=True,
            ),
            token_verifier=self._verifier,
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
        del exc_type, exc, traceback
        if self._channel is not None:
            await self._channel.close()
        if self._server is not None:
            await self._server.stop(grace=None)


def _verifier(
    *, scopes: tuple[str, ...], allowed_providers: list[str] | None = None
) -> StaticBearerTokenVerifier:
    if allowed_providers is None:
        allowed_providers = ["cli"]
    payload = json.dumps(
        [
            {
                "client_id": "cli-1",
                "token_sha256": hash_token("token-1"),
                "client_kind": "external_client",
                "provider": "cli",
                "allowed_providers": allowed_providers,
                "scopes": list(scopes),
                "observation_capabilities": [],
            }
        ]
    )
    return StaticBearerTokenVerifier.from_env({"TOKENS": payload}, "TOKENS")


def _request() -> runtime_pb2.SubmitObservationRequest:
    return runtime_pb2.SubmitObservationRequest(
        correlation_id="corr-1",
        observation=observations_pb2.Observation(
            observation_id="obs-1",
            session_id="session-1",
            kind=observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE,
            occurred_at=timestamp_from_datetime(_OCCURRED_AT),
            context=observations_pb2.ObservationContext(source="cli"),
            actor_message=observations_pb2.ActorMessagePayload(text="hello"),
        ),
    )


def _report_request() -> runtime_pb2.ReportActionResultRequest:
    return runtime_pb2.ReportActionResultRequest(
        delivery_id="delivery-1",
        lease_id="lease-1",
        action_id="action-1",
        correlation_id="corr-1",
        status="succeeded",
        external_message_id="msg-1",
    )


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


_OCCURRED_AT = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
