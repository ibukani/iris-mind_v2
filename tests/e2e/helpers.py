"""Process-level runtime E2E helpers."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from google.protobuf.timestamp_pb2 import Timestamp
import grpc
import pytest

from iris.generated.iris.api.v1 import identity_pb2, observations_pb2, spaces_pb2
from iris.generated.iris.runtime.v1 import runtime_pb2, runtime_pb2_grpc
from tests.e2e.runtime_process import (
    RUNTIME_HOST,
    RuntimeProcess,
    find_free_port,
    start_runtime_process,
    stop_runtime_process,
)
from tests.helpers.grpc_test import grpc_call

__all__ = [
    "RUNTIME_HOST",
    "RuntimeProcess",
    "assert_invalid_request",
    "build_cli_activity_event_request",
    "build_cli_presence_signal_request",
    "build_cli_submit_observation_request",
    "create_runtime_channel",
    "create_runtime_stub",
    "find_free_port",
    "get_runtime_info",
    "start_runtime_process",
    "stop_runtime_process",
    "submit_observation",
    "wait_for_runtime_ready",
    "write_runtime_config",
]

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from grpc import StatusCode

_DEFAULT_READY_TIMEOUT_SECONDS = 10.0


def create_runtime_channel(port: int) -> grpc.aio.Channel:
    """Create an insecure loopback gRPC channel for the runtime server.

    Returns:
        Async gRPC channel.
    """
    return grpc.aio.insecure_channel(f"{RUNTIME_HOST}:{port}")


def create_runtime_stub(channel: grpc.aio.Channel) -> runtime_pb2_grpc.IrisRuntimeServiceAsyncStub:
    """Create an Iris runtime gRPC stub.

    Returns:
        Runtime service stub.
    """
    return runtime_pb2_grpc.IrisRuntimeServiceStub(channel)


async def wait_for_runtime_ready(
    runtime: RuntimeProcess,
    *,
    timeout_seconds: float = _DEFAULT_READY_TIMEOUT_SECONDS,
) -> runtime_pb2.GetRuntimeInfoResponse:
    """Poll GetRuntimeInfo until the runtime server is ready.

    Returns:
        Runtime metadata response from ``GetRuntimeInfo``.
    """
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    channel = create_runtime_channel(runtime.port)
    stub = create_runtime_stub(channel)

    try:
        return await _poll_runtime_ready(runtime=runtime, stub=stub, deadline=deadline)
    finally:
        await channel.close()


async def get_runtime_info(port: int) -> runtime_pb2.GetRuntimeInfoResponse:
    """Open a channel, call GetRuntimeInfo once, and close the channel.

    Returns:
        GetRuntimeInfo response from the runtime.
    """
    channel = create_runtime_channel(port)
    try:
        stub = create_runtime_stub(channel)
        response = await grpc_call(stub.GetRuntimeInfo(runtime_pb2.GetRuntimeInfoRequest()))
    finally:
        await channel.close()
    assert isinstance(response, runtime_pb2.GetRuntimeInfoResponse)
    return response


async def assert_invalid_request(
    port: int,
    request: runtime_pb2.SubmitObservationRequest,
) -> None:
    """Assert that a SubmitObservation request fails with INVALID_ARGUMENT."""
    channel = create_runtime_channel(port)
    try:
        stub = create_runtime_stub(channel)
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await grpc_call(stub.SubmitObservation(request))
    finally:
        await channel.close()
    assert exc_info.value.code() is grpc.StatusCode.INVALID_ARGUMENT


def build_cli_submit_observation_request(
    *,
    correlation_id: str = "e2e-corr-1",
    observation_id: str = "e2e-obs-1",
    session_id: str = "e2e-session-1",
    external_message_id: str = "e2e-message-1",
    text: str = "hello from process e2e",
) -> runtime_pb2.SubmitObservationRequest:
    """Build a CLI-like SubmitObservation request.

    Returns:
        SubmitObservation request with CLI-style actor message context.
    """
    occurred_at = Timestamp()
    occurred_at.FromDatetime(datetime(2026, 6, 10, 12, 0, tzinfo=UTC))

    return runtime_pb2.SubmitObservationRequest(
        correlation_id=correlation_id,
        observation=observations_pb2.Observation(
            observation_id=observation_id,
            session_id=session_id,
            kind=observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE,
            occurred_at=occurred_at,
            context=observations_pb2.ObservationContext(
                source="cli",
                account_ref=identity_pb2.ExternalAccountRef(
                    provider="cli",
                    provider_subject="local-user",
                    display_name="Local User",
                    actor_kind=identity_pb2.ACTOR_KIND_HUMAN,
                ),
                space_ref=spaces_pb2.ExternalSpaceRef(
                    provider="cli",
                    provider_space_ref="cli-session-1",
                    display_name="CLI Session",
                    space_kind=spaces_pb2.SPACE_KIND_DIRECT_MESSAGE,
                ),
            ),
            actor_message=observations_pb2.ActorMessagePayload(
                text=text,
                external_message_id=external_message_id,
            ),
        ),
    )


def write_runtime_config(
    *,
    path: Path,
    backend: str,
    sqlite_path: Path | None = None,
    models: Mapping[str, str] | None = None,
) -> Path:
    """Write a runtime TOML config for E2E process tests.

    ``backend`` and ``sqlite_path`` must be consistent. Callers must pass
    ``backend`` explicitly so the resulting config is never ambiguous.

    Returns:
        Path to the written TOML config file.

    Raises:
        ValueError: ``backend='sqlite'`` is set without ``sqlite_path``, or
            ``sqlite_path`` is set with a non-sqlite backend.
    """
    if backend == "sqlite":
        if sqlite_path is None:
            message = "sqlite_path is required when backend='sqlite'"
            raise ValueError(message)
        state_section = f'[state]\nbackend = "sqlite"\nsqlite_path = "{sqlite_path}"\n'
    else:
        if sqlite_path is not None:
            message = f"sqlite_path is only valid when backend='sqlite', got backend={backend!r}"
            raise ValueError(message)
        state_section = f'[state]\nbackend = "{backend}"\n'
    model_lines: list[str] = []
    for slot, provider in (models or {"default_chat": "fake"}).items():
        model_lines.append(f'[models.{slot}]\nprovider = "{provider}"\nmodel = "fake-llm"\n')
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        '[server]\nhost = "127.0.0.1"\nlocal_only = true\n\n'
        f"{state_section}\n"
        f"{''.join(model_lines)}\n"
        '[logging]\nlevel = "WARNING"\nformat = "text"\n\n'
        '[safety]\nmode = "development"\n'
    )
    path.write_text(body, encoding="utf-8")
    return path


def build_cli_presence_signal_request(
    *,
    correlation_id: str,
    observation_id: str,
    session_id: str,
    status: observations_pb2.PresenceStatus.ValueType,
) -> runtime_pb2.SubmitObservationRequest:
    """Build a CLI-like presence_signal SubmitObservation request.

    Returns:
        SubmitObservation request with presence_signal payload and CLI context.
    """
    return _build_cli_request(
        correlation_id=correlation_id,
        observation_id=observation_id,
        session_id=session_id,
        kind=observations_pb2.OBSERVATION_KIND_PRESENCE_SIGNAL,
        payload_field="presence_signal",
        payload_message=observations_pb2.PresenceSignalPayload(status=status),
    )


def build_cli_activity_event_request(
    *,
    correlation_id: str,
    observation_id: str,
    session_id: str,
    activity_kind: observations_pb2.ActivityKind.ValueType,
) -> runtime_pb2.SubmitObservationRequest:
    """Build a CLI-like activity_event SubmitObservation request.

    Returns:
        SubmitObservation request with activity_event payload and CLI context.
    """
    return _build_cli_request(
        correlation_id=correlation_id,
        observation_id=observation_id,
        session_id=session_id,
        kind=observations_pb2.OBSERVATION_KIND_ACTIVITY_EVENT,
        payload_field="activity_event",
        payload_message=observations_pb2.ActivityEventPayload(
            activity_kind=activity_kind,
            provider_event_id="evt-1",
            provider_sequence=1,
        ),
    )


async def submit_observation(
    *,
    port: int,
    request: runtime_pb2.SubmitObservationRequest,
) -> runtime_pb2.SubmitObservationResponse:
    """Open a gRPC channel, submit a request, and close the channel.

    Returns:
        SubmitObservation response from the runtime.
    """
    channel = create_runtime_channel(port)
    try:
        stub = create_runtime_stub(channel)
        response = await grpc_call(stub.SubmitObservation(request))
    finally:
        await channel.close()
    assert isinstance(response, runtime_pb2.SubmitObservationResponse)
    return response


def _build_cli_request(
    *,
    correlation_id: str,
    observation_id: str,
    session_id: str,
    kind: observations_pb2.ObservationKind.ValueType,
    payload_field: str,
    payload_message: _PayloadMessage,
) -> runtime_pb2.SubmitObservationRequest:
    """Build a CLI-style SubmitObservation request with the given payload oneof.

    Returns:
        SubmitObservation request with the supplied oneof payload.
    """
    occurred_at = Timestamp()
    occurred_at.FromDatetime(datetime(2026, 6, 10, 12, 0, tzinfo=UTC))
    context = observations_pb2.ObservationContext(
        source="cli",
        account_ref=identity_pb2.ExternalAccountRef(
            provider="cli",
            provider_subject="local-user",
            display_name="Local User",
            actor_kind=identity_pb2.ACTOR_KIND_HUMAN,
        ),
        space_ref=spaces_pb2.ExternalSpaceRef(
            provider="cli",
            provider_space_ref="cli-session-1",
            display_name="CLI Session",
            space_kind=spaces_pb2.SPACE_KIND_DIRECT_MESSAGE,
        ),
    )
    observation = observations_pb2.Observation(
        observation_id=observation_id,
        session_id=session_id,
        kind=kind,
        occurred_at=occurred_at,
        context=context,
    )
    _set_oneof_payload(observation, payload_field, payload_message)
    return runtime_pb2.SubmitObservationRequest(
        correlation_id=correlation_id,
        observation=observation,
    )


def _set_oneof_payload(
    observation: observations_pb2.Observation,
    payload_field: str,
    payload_message: _PayloadMessage,
) -> None:
    """Set a payload oneof field on an Observation using MergeFrom.

    Python protobuf rejects dynamic ``setattr`` on message oneof fields, so
    we construct a partial sibling Observation and merge the payload in.

    Raises:
        TypeError: ``payload_field`` is not a known payload oneof name.
    """
    partial = observations_pb2.Observation()
    if payload_field == "actor_message" and isinstance(
        payload_message, observations_pb2.ActorMessagePayload
    ):
        partial.actor_message.CopyFrom(payload_message)
    elif payload_field == "idle_tick" and isinstance(
        payload_message, observations_pb2.IdleTickPayload
    ):
        partial.idle_tick.CopyFrom(payload_message)
    elif payload_field == "activity_event" and isinstance(
        payload_message, observations_pb2.ActivityEventPayload
    ):
        partial.activity_event.CopyFrom(payload_message)
    elif payload_field == "presence_signal" and isinstance(
        payload_message, observations_pb2.PresenceSignalPayload
    ):
        partial.presence_signal.CopyFrom(payload_message)
    else:
        message = f"unsupported payload field: {payload_field!r}"
        raise TypeError(message)
    observation.MergeFrom(partial)


async def _collect_runtime_output(runtime: RuntimeProcess) -> None:
    await runtime.stop()


async def _poll_runtime_ready(
    *,
    runtime: RuntimeProcess,
    stub: runtime_pb2_grpc.IrisRuntimeServiceAsyncStub,
    deadline: float,
) -> runtime_pb2.GetRuntimeInfoResponse:
    last_error: str | None = None
    while asyncio.get_running_loop().time() < deadline:
        if not runtime.is_alive():
            await _collect_runtime_output(runtime)
            _raise_process_exited_before_ready(runtime)

        try:
            response = await asyncio.wait_for(
                grpc_call(stub.GetRuntimeInfo(runtime_pb2.GetRuntimeInfoRequest())),
                timeout=1.0,
            )
            assert isinstance(response, runtime_pb2.GetRuntimeInfoResponse)
        except grpc.aio.AioRpcError as exc:
            last_error = _format_rpc_error(exc.code(), exc.details())
        except TimeoutError as exc:
            last_error = str(exc)
        else:
            return response

        await asyncio.sleep(0.1)

    # Best-effort: collect any captured output to help debug slow startups.
    if not runtime.is_alive():
        await _collect_runtime_output(runtime)
    message = (
        f"runtime server did not become ready; last_error={last_error!r}; "
        f"returncode={runtime.returncode}; "
        f"stdout={runtime.stdout!r}; stderr={runtime.stderr!r}"
    )
    raise AssertionError(message)


def _raise_process_exited_before_ready(runtime: RuntimeProcess) -> None:
    message = (
        "runtime server exited before readiness; "
        f"returncode={runtime.returncode}; "
        f"stdout={runtime.stdout!r}; stderr={runtime.stderr!r}"
    )
    raise AssertionError(message)


def _format_rpc_error(code: StatusCode, details: str | None) -> str:
    return f"{code.name}: {details}"


if TYPE_CHECKING:
    _PayloadMessage = (
        observations_pb2.ActorMessagePayload
        | observations_pb2.IdleTickPayload
        | observations_pb2.ActivityEventPayload
        | observations_pb2.PresenceSignalPayload
    )
