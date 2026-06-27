"""gRPC auth interceptor integration tests."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import socket
from typing import TYPE_CHECKING

import grpc
import pytest

from iris.adapters.grpc.mappers import timestamp_from_datetime

if TYPE_CHECKING:
    from types import TracebackType
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


class _AuthGrpcHarness:
    """In-process gRPC server with required auth."""

    def __init__(
        self,
        verifier: StaticBearerTokenVerifier,
        *,
        runtime_service: RecordingRuntimeService | None = None,
    ) -> None:
        self._verifier = verifier
        self._runtime_service = runtime_service or RecordingRuntimeService("unused")
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


def _verifier(*, scopes: tuple[str, ...]) -> StaticBearerTokenVerifier:
    payload = json.dumps(
        [
            {
                "client_id": "cli-1",
                "token_sha256": hash_token("token-1"),
                "client_kind": "external_client",
                "provider": "cli",
                "allowed_providers": ["cli"],
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


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


_OCCURRED_AT = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
