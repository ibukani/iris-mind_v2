"""Process-level runtime E2E helpers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import os
import shutil
import socket
import subprocess  # noqa: S404 -- E2E helpers manage fixed local runtime subprocesses.
from typing import TYPE_CHECKING

from google.protobuf.timestamp_pb2 import Timestamp
import grpc

from iris.generated.iris.api.v1 import identity_pb2, observations_pb2, spaces_pb2
from iris.generated.iris.runtime.v1 import runtime_pb2, runtime_pb2_grpc
from tests.helpers.grpc_test import grpc_call

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from grpc import StatusCode

_RUNTIME_HOST = "127.0.0.1"
_DEFAULT_READY_TIMEOUT_SECONDS = 10.0
_STOP_TIMEOUT_SECONDS = 5.0
_UV_NOT_FOUND_MESSAGE = "uv executable not found"


@dataclass
class RuntimeProcess:
    """Runtime subprocess state for E2E failure reporting."""

    process: subprocess.Popen[str]
    port: int
    stdout: str | None = None
    stderr: str | None = None


def find_free_port() -> int:
    """Return a free loopback TCP port.

    Returns:
        Free TCP port number.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((_RUNTIME_HOST, 0))
        return int(sock.getsockname()[1])


def start_runtime_process(
    *,
    port: int,
    repo_root: Path,
    runtime_home: Path,
    config_path: Path | None = None,
    extra_env: Mapping[str, str] | None = None,
) -> RuntimeProcess:
    """Start the runtime server as a real subprocess.

    Returns:
        Runtime subprocess wrapper.

    Raises:
        RuntimeError: ``uv`` is not available on ``PATH``.
    """
    uv_path = shutil.which("uv")
    if uv_path is None:
        raise RuntimeError(_UV_NOT_FOUND_MESSAGE)

    command = [
        uv_path,
        "run",
        "--project",
        str(repo_root),
        "python",
        "-m",
        "iris.runtime.server",
        "--host",
        _RUNTIME_HOST,
        "--port",
        str(port),
    ]
    if config_path is not None:
        command.extend(("--config", str(config_path)))

    process = subprocess.Popen(  # noqa: S603 -- E2E runs a fixed uv command tuple.
        command,
        cwd=runtime_home,
        env=_runtime_env(runtime_home=runtime_home, extra_env=extra_env),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return RuntimeProcess(process=process, port=port)


def create_runtime_channel(port: int) -> grpc.aio.Channel:
    """Create an insecure loopback gRPC channel for the runtime server.

    Returns:
        Async gRPC channel.
    """
    return grpc.aio.insecure_channel(f"{_RUNTIME_HOST}:{port}")


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


async def stop_runtime_process(
    runtime: RuntimeProcess,
    *,
    timeout_seconds: float = _STOP_TIMEOUT_SECONDS,
) -> tuple[str, str]:
    """Terminate a runtime subprocess and return captured stdout and stderr.

    Returns:
        Captured ``stdout`` and ``stderr``.
    """
    if runtime.process.poll() is None:
        runtime.process.terminate()
        try:
            stdout, stderr = await asyncio.wait_for(
                asyncio.to_thread(runtime.process.communicate),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            runtime.process.kill()
            stdout, stderr = await asyncio.to_thread(runtime.process.communicate)
    else:
        stdout, stderr = await asyncio.to_thread(runtime.process.communicate)

    runtime.stdout = stdout
    runtime.stderr = stderr
    return stdout, stderr


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


def _runtime_env(*, runtime_home: Path, extra_env: Mapping[str, str] | None) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("IRIS_MIND_CONFIG", None)
    env["XDG_CONFIG_HOME"] = str(runtime_home / "xdg-config")
    env["HOME"] = str(runtime_home / "home")
    env["UV_CACHE_DIR"] = str(runtime_home / "uv-cache")
    if extra_env is not None:
        env.update(extra_env)
    return env


async def _collect_runtime_output(runtime: RuntimeProcess) -> None:
    stdout, stderr = await asyncio.to_thread(runtime.process.communicate)
    runtime.stdout = stdout
    runtime.stderr = stderr


async def _poll_runtime_ready(
    *,
    runtime: RuntimeProcess,
    stub: runtime_pb2_grpc.IrisRuntimeServiceAsyncStub,
    deadline: float,
) -> runtime_pb2.GetRuntimeInfoResponse:
    last_error: str | None = None
    while asyncio.get_running_loop().time() < deadline:
        if runtime.process.poll() is not None:
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

    message = f"runtime server did not become ready; last_error={last_error!r}"
    raise AssertionError(message)


def _raise_process_exited_before_ready(runtime: RuntimeProcess) -> None:
    message = (
        "runtime server exited before readiness; "
        f"returncode={runtime.process.returncode}; "
        f"stdout={runtime.stdout!r}; stderr={runtime.stderr!r}"
    )
    raise AssertionError(message)


def _format_rpc_error(code: StatusCode, details: str | None) -> str:
    return f"{code.name}: {details}"
