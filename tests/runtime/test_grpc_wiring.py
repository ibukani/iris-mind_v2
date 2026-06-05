"""Runtime gRPC wiring tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, override

import grpc
import pytest

from iris.adapters.app_gateway.fake_resolvers import FakeIdentityResolver
from iris.adapters.grpc.mappers import GrpcRuntimeMapper, timestamp_from_datetime
from iris.adapters.grpc.server import IrisRuntimeGrpcServicer
from iris.contracts.actions import PresentedOutput
from iris.generated.iris.api.v1 import identity_pb2, observations_pb2
from iris.generated.iris.runtime.v1 import runtime_pb2, runtime_pb2_grpc
from iris.runtime.service import IrisRuntimeService, RuntimeResponse
from iris.runtime.wiring.grpc import add_iris_runtime_servicer, create_grpc_server

if TYPE_CHECKING:
    from iris.runtime.service import ObservationEnvelope


_OCCURRED_AT = datetime(2026, 6, 5, 14, 0, tzinfo=UTC)


@pytest.mark.anyio
async def test_add_iris_runtime_servicer_registers_servicer_without_resolver() -> None:
    """resolver未注入でもservicerが登録され、actor_refはINVALID_ARGUMENTになることを確認する。"""
    server = grpc.aio.server()
    add_iris_runtime_servicer(server, _RecordingRuntimeService("ok"))
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = runtime_pb2_grpc.IrisRuntimeServiceStub(channel)
            with pytest.raises(grpc.aio.AioRpcError) as exc_info:
                await stub.SubmitObservation(_actor_ref_request())
        assert exc_info.value.code() is grpc.StatusCode.INVALID_ARGUMENT
    finally:
        await server.stop(0)


@pytest.mark.anyio
async def test_add_iris_runtime_servicer_uses_injected_resolver() -> None:
    """注入されたresolverでactor_refが解決されることを確認する。"""
    runtime_service = _RecordingRuntimeService("resolved")
    server = grpc.aio.server()
    add_iris_runtime_servicer(server, runtime_service, identity_resolver=FakeIdentityResolver())
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    response = await _submit_actor_ref(port)
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
        _RecordingRuntimeService("created"),
        port=0,
        identity_resolver=FakeIdentityResolver(),
    )
    await server.start()
    await server.stop(0)
    assert server is not None


@pytest.mark.anyio
async def test_servicer_construction_uses_injected_mapper() -> None:
    """constructorへ渡したmapperがactor_ref解決に使われることを確認する。"""
    runtime_service = _RecordingRuntimeService("mapper")
    mapper = GrpcRuntimeMapper(identity_resolver=FakeIdentityResolver())
    servicer = IrisRuntimeGrpcServicer(runtime_service, mapper=mapper)
    server = grpc.aio.server()
    runtime_pb2_grpc.add_IrisRuntimeServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    response = await _submit_actor_ref(port)
    try:
        assert response.output.text == "mapper"
    finally:
        await server.stop(0)


async def _submit_actor_ref(port: int) -> runtime_pb2.SubmitObservationResponse:
    """actor_ref付きSubmitObservationをinsecure channel経由で送信する。

    Args:
        port: insecure gRPC serverのバインドport。

    Returns:
        runtime_pb2.SubmitObservationResponse: server response DTO.
    """
    async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
        stub = runtime_pb2_grpc.IrisRuntimeServiceStub(channel)
        return await stub.SubmitObservation(_actor_ref_request())


def _actor_ref_request() -> runtime_pb2.SubmitObservationRequest:
    """actor_ref付きActorMessage SubmitObservationRequest fixtureを作る。

    Returns:
        runtime_pb2.SubmitObservationRequest: Actor message request DTO with actor_ref.
    """
    return runtime_pb2.SubmitObservationRequest(
        correlation_id="corr-1",
        observation=observations_pb2.Observation(
            observation_id="obs-1",
            session_id="session-1",
            kind=observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE,
            occurred_at=timestamp_from_datetime(_OCCURRED_AT),
            context=observations_pb2.ObservationContext(
                actor_ref=identity_pb2.ExternalActorRef(
                    provider="discord",
                    provider_subject="12345",
                    display_name="Mina",
                ),
            ),
            actor_message=observations_pb2.ActorMessagePayload(text="hello grpc"),
        ),
    )


class _RecordingRuntimeService(IrisRuntimeService):
    """Fake runtime service that records envelopes and returns fixed output."""

    def __init__(self, text: str) -> None:
        """Initialize with fixed response text."""
        self._text = text
        self.envelope: ObservationEnvelope | None = None

    @override
    async def handle_observation(self, envelope: ObservationEnvelope) -> RuntimeResponse:
        """Record envelope and return fixed RuntimeResponse.

        Returns:
            RuntimeResponse: Fixed runtime response.
        """
        self.envelope = envelope
        return RuntimeResponse(
            output=PresentedOutput(text=self._text),
            correlation_id=envelope.correlation_id,
        )
