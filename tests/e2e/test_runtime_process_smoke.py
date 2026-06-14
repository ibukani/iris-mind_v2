"""Runtime process smoke E2E tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from iris.generated.iris.runtime.v1 import runtime_pb2
from tests.e2e.helpers import (
    build_cli_submit_observation_request,
    create_runtime_channel,
    create_runtime_stub,
    find_free_port,
    start_runtime_process,
    stop_runtime_process,
    wait_for_runtime_ready,
)
from tests.helpers.grpc_test import grpc_call

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.e2e
@pytest.mark.anyio
async def test_runtime_process_starts_and_returns_runtime_info(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """Runtime subprocess exposes metadata over gRPC."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        response = await wait_for_runtime_ready(runtime)
    finally:
        await stop_runtime_process(runtime)

    _assert_runtime_info(response)


@pytest.mark.e2e
@pytest.mark.anyio
async def test_runtime_process_accepts_cli_like_submit_observation(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """Runtime subprocess accepts a CLI-like SubmitObservation request."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        response = await _submit_cli_observation(runtime.port)
    finally:
        await stop_runtime_process(runtime)

    assert response.correlation_id == "e2e-corr-1"
    assert response.output.text is not None
    assert response.output.text.strip()


@pytest.mark.e2e
@pytest.mark.anyio
async def test_runtime_process_shutdown_does_not_leave_child_process(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """Runtime subprocess cleanup leaves no child process running."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
    finally:
        await stop_runtime_process(runtime)

    assert not runtime.is_alive()


def _assert_runtime_info(response: runtime_pb2.GetRuntimeInfoResponse) -> None:
    assert response.runtime_name == "iris-mind"
    assert response.runtime_version == "0.1.0"
    assert response.api_version == "iris.runtime.v1"
    assert "submit_observation" in response.supported_features
    assert "persistent_account" in response.supported_features
    assert "ephemeral_space" in response.supported_features


async def _submit_cli_observation(port: int) -> runtime_pb2.SubmitObservationResponse:
    channel = create_runtime_channel(port)
    try:
        stub = create_runtime_stub(channel)
        response = await grpc_call(stub.SubmitObservation(build_cli_submit_observation_request()))
        assert isinstance(response, runtime_pb2.SubmitObservationResponse)
        return response
    finally:
        await channel.close()
