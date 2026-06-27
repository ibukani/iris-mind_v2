"""Runtime gRPC wiring tests."""

from __future__ import annotations

from datetime import UTC, datetime

import grpc
import pytest

from iris.adapters.app_gateway.fake_resolvers import FakeIdentityResolver
from iris.adapters.grpc.mappers import GrpcRuntimeMapper, timestamp_from_datetime
from iris.adapters.grpc.server import IrisRuntimeGrpcServicer
from iris.generated.iris.api.v1 import identity_pb2, observations_pb2
from iris.generated.iris.runtime.v1 import runtime_pb2, runtime_pb2_grpc
from iris.runtime.wiring.grpc import add_iris_runtime_servicer, create_grpc_server
from tests.helpers.grpc_test import RecordingRuntimeService

_OCCURRED_AT = datetime(2026, 6, 5, 14, 0, tzinfo=UTC)


@pytest.mark.anyio
async def test_add_iris_runtime_servicer_registers_servicer_without_resolver() -> None:
    """resolver未注入でもservicerが登録され、account_refはINVALID_ARGUMENTになることを確認する。"""
    server = grpc.aio.server()
    add_iris_runtime_servicer(server, RecordingRuntimeService("ok"))
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = runtime_pb2_grpc.IrisRuntimeServiceStub(channel)
            with pytest.raises(grpc.aio.AioRpcError) as exc_info:
                await stub.SubmitObservation(_account_ref_request())
        assert exc_info.value.code() is grpc.StatusCode.INVALID_ARGUMENT
    finally:
        await server.stop(0)


@pytest.mark.anyio
async def test_add_iris_runtime_servicer_uses_injected_resolver() -> None:
    """注入されたresolverでaccount_refが解決されることを確認する。"""
    runtime_service = RecordingRuntimeService("resolved")
    server = grpc.aio.server()
    add_iris_runtime_servicer(server, runtime_service, identity_resolver=FakeIdentityResolver())
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    response = await _submit_account_ref(port)
    try:
        assert response.output.text == "resolved"
        assert runtime_service.envelope is not None
        actor = runtime_service.envelope.observation.context.actor
        assert actor is not None
        assert actor.provider == "discord"
    finally:
        await server.stop(0)


@pytest.mark.anyio
async def test_create_grpc_server_returns_started_server() -> None:
    """create_grpc_serverがservicerを内包したserverを返すことを確認する。"""
    server = create_grpc_server(
        RecordingRuntimeService("created"),
        port=0,
        identity_resolver=FakeIdentityResolver(),
    )
    await server.start()
    await server.stop(0)
    assert server is not None


def test_create_grpc_server_raises_when_bind_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """create_grpc_serverがbind失敗をRuntimeErrorにすることを確認する。"""

    class _UnboundServer:
        def __init__(self, *args: object, **kwargs: object) -> None:
            _ = args, kwargs

        def add_generic_rpc_handlers(self, handlers: object) -> None:
            """Accept generated service registration."""
            _ = handlers

        def add_registered_method_handlers(
            self,
            service_name: str,
            method_handlers: object,
        ) -> None:
            """Accept generated registered method handler registration."""
            _ = service_name, method_handlers

        def add_insecure_port(self, address: str) -> int:
            """Return gRPC bind failure sentinel.

            Returns:
                0, matching grpc add_insecure_port bind failure.
            """
            _ = address
            return 0

    monkeypatch.setattr(grpc.aio, "server", _UnboundServer)

    with pytest.raises(
        RuntimeError,
        match=r"failed to bind gRPC port 127\.0\.0\.1:50051",
    ):
        create_grpc_server(RecordingRuntimeService("unused"))


@pytest.mark.anyio
async def test_servicer_construction_uses_injected_mapper() -> None:
    """constructorへ渡したmapperがaccount_ref解決に使われることを確認する。"""
    runtime_service = RecordingRuntimeService("mapper")
    mapper = GrpcRuntimeMapper(identity_resolver=FakeIdentityResolver())
    servicer = IrisRuntimeGrpcServicer(runtime_service, mapper=mapper)
    server = grpc.aio.server()
    runtime_pb2_grpc.add_IrisRuntimeServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    response = await _submit_account_ref(port)
    try:
        assert response.output.text == "mapper"
    finally:
        await server.stop(0)


async def _submit_account_ref(port: int) -> runtime_pb2.SubmitObservationResponse:
    """account_ref付きSubmitObservationをinsecure channel経由で送信する。

    Args:
        port: insecure gRPC serverのバインドport。

    Returns:
        runtime_pb2.SubmitObservationResponse: server response DTO.
    """
    async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
        stub = runtime_pb2_grpc.IrisRuntimeServiceStub(channel)
        return await stub.SubmitObservation(_account_ref_request())


def _account_ref_request() -> runtime_pb2.SubmitObservationRequest:
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
                    provider="discord",
                    provider_subject="12345",
                    display_name="Mina",
                ),
            ),
            actor_message=observations_pb2.ActorMessagePayload(text="hello grpc"),
        ),
    )
