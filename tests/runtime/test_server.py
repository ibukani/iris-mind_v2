"""Tests for runtime server entrypoint."""

from __future__ import annotations

import asyncio
import contextlib
import socket
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import grpc
import pytest

from iris.adapters.grpc.mappers import timestamp_from_datetime
from iris.generated.iris.api.v1 import identity_pb2, observations_pb2

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from iris.generated.iris.runtime.v1 import runtime_pb2, runtime_pb2_grpc
from iris.runtime.config import RuntimeConfigOverrides
from iris.runtime.server import serve


@contextlib.asynccontextmanager
async def background_server(port: int) -> AsyncGenerator[None]:
    """Run the runtime gRPC server in the background."""
    task = asyncio.create_task(
        serve(
            overrides=RuntimeConfigOverrides(
                server_host="127.0.0.1",
                server_port=port,
            ),
        )
    )
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def _free_tcp_port() -> int:
    """Return an available local TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.anyio
async def test_server_starts_and_handles_observation() -> None:
    """Test the server starts and handles a basic gRPC observation submission."""
    port = _free_tcp_port()
    async with background_server(port):
        channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
        await channel.channel_ready()
        stub = runtime_pb2_grpc.IrisRuntimeServiceStub(channel)

        request = runtime_pb2.SubmitObservationRequest(
            correlation_id="corr-1",
            observation=observations_pb2.Observation(
                observation_id="obs-1",
                session_id="session-1",
                kind=observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE,
                occurred_at=timestamp_from_datetime(datetime(2026, 6, 5, tzinfo=UTC)),
                context=observations_pb2.ObservationContext(
                    account_ref=identity_pb2.ExternalAccountRef(
                        provider="test",
                        provider_subject="test-user",
                        display_name="Tester",
                    ),
                ),
                actor_message=observations_pb2.ActorMessagePayload(
                    text="hello",
                ),
            ),
        )

        response = await stub.SubmitObservation(request)

        assert isinstance(response, runtime_pb2.SubmitObservationResponse)
        assert response.output.text

        await channel.close()
