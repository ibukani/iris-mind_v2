"""Runtime gRPC ingress integration tests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast, override

import grpc
import pytest

from iris.adapters.grpc.mappers import timestamp_from_datetime
from iris.adapters.grpc.server import IrisRuntimeGrpcServicer
from iris.contracts.actions import PresentedOutput
from iris.generated.iris.api.v1 import observations_pb2
from iris.generated.iris.runtime.v1 import runtime_pb2, runtime_pb2_grpc
from iris.runtime.service import IrisRuntimeService, RuntimeResponse

if TYPE_CHECKING:
    from types import TracebackType

    from iris.runtime.service import ObservationEnvelope


_AsyncSubmitObservation = Callable[
    [runtime_pb2.SubmitObservationRequest],
    Awaitable[runtime_pb2.SubmitObservationResponse],
]

_OCCURRED_AT = datetime(2026, 6, 5, 13, 0, tzinfo=UTC)


@pytest.mark.anyio
async def test_submit_observation_returns_presented_output() -> None:
    """SubmitObservationがRuntimeServiceへ委譲しPresentedOutputを返すことを確認する。"""
    runtime_service = _RecordingRuntimeService("grpc response")

    async with _GrpcRuntimeHarness(runtime_service) as submit_observation:
        response = await submit_observation(_actor_message_request())

    assert runtime_service.envelope is not None
    assert runtime_service.envelope.observation.kind.value == "actor_message"
    assert response.correlation_id == "corr-1"
    assert response.output.text == "grpc response"


@pytest.mark.anyio
async def test_submit_observation_invalid_request_returns_invalid_argument() -> None:
    """Invalid proto inputがINVALID_ARGUMENTになることを確認する。"""
    async with _GrpcRuntimeHarness(_RecordingRuntimeService("unused")) as submit_observation:
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await submit_observation(
                runtime_pb2.SubmitObservationRequest(
                    correlation_id="corr-1",
                    observation=observations_pb2.Observation(
                        observation_id="obs-1",
                        session_id="session-1",
                        kind=observations_pb2.OBSERVATION_KIND_UNSPECIFIED,
                        occurred_at=timestamp_from_datetime(_OCCURRED_AT),
                    ),
                )
            )

    assert exc_info.value.code() is grpc.StatusCode.INVALID_ARGUMENT


@pytest.mark.anyio
async def test_submit_observation_runtime_failure_returns_internal() -> None:
    """Runtime service failureがINTERNALになることを確認する。"""
    async with _GrpcRuntimeHarness(_FailingRuntimeService()) as submit_observation:
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await submit_observation(_actor_message_request())

    assert exc_info.value.code() is grpc.StatusCode.INTERNAL


def _actor_message_request() -> runtime_pb2.SubmitObservationRequest:
    """ActorMessage SubmitObservationRequest fixtureを作る。

    Returns:
        runtime_pb2.SubmitObservationRequest: Actor message request DTO。
    """
    return runtime_pb2.SubmitObservationRequest(
        correlation_id="corr-1",
        observation=observations_pb2.Observation(
            observation_id="obs-1",
            session_id="session-1",
            kind=observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE,
            occurred_at=timestamp_from_datetime(_OCCURRED_AT),
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


class _FailingRuntimeService(IrisRuntimeService):
    """Fake runtime service that raises to exercise INTERNAL mapping."""

    def __init__(self) -> None:
        """Initialize failing service recording slot."""
        self.envelope: ObservationEnvelope | None = None

    @override
    async def handle_observation(self, envelope: ObservationEnvelope) -> RuntimeResponse:
        """Raise a runtime failure.

        Raises:
            RuntimeError: Always raised for test.
        """
        self.envelope = envelope
        message = "boom"
        raise RuntimeError(message)


class _GrpcRuntimeHarness:
    """Async context manager for an in-process grpc.aio test server."""

    def __init__(self, runtime_service: IrisRuntimeService) -> None:
        """Create harness around a fake runtime service."""
        self._runtime_service = runtime_service
        self._server: grpc.aio.Server | None = None
        self._channel: grpc.aio.Channel | None = None

    async def __aenter__(self) -> _AsyncSubmitObservation:
        """Start server and return a connected stub.

        Returns:
            runtime_pb2_grpc.IrisRuntimeServiceStub: Connected gRPC stub.
        """
        server = grpc.aio.server()
        runtime_pb2_grpc.add_IrisRuntimeServiceServicer_to_server(
            IrisRuntimeGrpcServicer(self._runtime_service),
            server,
        )
        port = server.add_insecure_port("127.0.0.1:0")
        await server.start()
        channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
        self._server = server
        self._channel = channel
        stub = runtime_pb2_grpc.IrisRuntimeServiceStub(channel)
        return cast("_AsyncSubmitObservation", stub.SubmitObservation)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close client channel and stop server."""
        _ = exc_type, exc, traceback
        if self._channel is not None:
            await self._channel.close()
        if self._server is not None:
            await self._server.stop(0)
