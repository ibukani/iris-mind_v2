"""Runtime API E2E contract tests for GetRuntimeInfo and SubmitObservation.

These tests spin up a real runtime subprocess and assert the external
gRPC contract: stable metadata, correlation_id echo, valid PresentedOutput,
and multi-request liveness for CLI-shaped actor_message requests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.e2e.helpers import (
    build_cli_submit_observation_request,
    find_free_port,
    get_runtime_info,
    start_runtime_process,
    stop_runtime_process,
    submit_observation,
    wait_for_runtime_ready,
)

if TYPE_CHECKING:
    from pathlib import Path

    from iris.generated.iris.runtime.v1 import runtime_pb2


@pytest.mark.e2e
@pytest.mark.anyio
async def test_get_runtime_info_returns_iris_mind_metadata(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """GetRuntimeInfo exposes stable iris-mind metadata for iris-cli_v2."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        response = await wait_for_runtime_ready(runtime)
    finally:
        await stop_runtime_process(runtime)

    assert response.runtime_name == "iris-mind"
    assert response.api_version == "iris.runtime.v1"
    assert response.runtime_version, "runtime_version must be non-empty"
    assert "submit_observation" in response.supported_features
    assert "persistent_account" in response.supported_features
    assert "ephemeral_space" in response.supported_features


@pytest.mark.e2e
@pytest.mark.anyio
async def test_get_runtime_info_repeated_call_keeps_runtime_healthy(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """GetRuntimeInfo stays valid across multiple calls without affecting the runtime."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        first = await wait_for_runtime_ready(runtime)
        second = await get_runtime_info(runtime.port)
        third = await get_runtime_info(runtime.port)
        assert runtime.is_alive()
    finally:
        await stop_runtime_process(runtime)

    assert first.runtime_name == "iris-mind"
    assert second.runtime_name == "iris-mind"
    assert third.runtime_name == "iris-mind"
    assert first.api_version == second.api_version == third.api_version
    assert first.supported_features == second.supported_features == third.supported_features


@pytest.mark.e2e
@pytest.mark.anyio
async def test_submit_observation_actor_message_echoes_correlation_id(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """SubmitObservation response echoes the client-supplied correlation_id."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        response = await submit_observation(
            port=runtime.port,
            request=build_cli_submit_observation_request(
                correlation_id="api-contract-corr-1",
            ),
        )
    finally:
        await stop_runtime_process(runtime)

    assert response.correlation_id == "api-contract-corr-1"


@pytest.mark.e2e
@pytest.mark.anyio
async def test_submit_observation_actor_message_returns_presented_output(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """SubmitObservation response carries a valid PresentedOutput for actor_message."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        response = await submit_observation(
            port=runtime.port,
            request=build_cli_submit_observation_request(
                text="hello api contract",
            ),
        )
    finally:
        await stop_runtime_process(runtime)

    assert response.HasField("output")
    assert response.output.text.strip()


@pytest.mark.e2e
@pytest.mark.anyio
async def test_submit_observation_multiple_requests_keep_server_alive(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """Repeated SubmitObservation calls in one session keep the runtime healthy."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        responses = await _submit_multi_requests(runtime.port)
        assert runtime.is_alive()
        metadata = await get_runtime_info(runtime.port)
        assert metadata.runtime_name == "iris-mind"
    finally:
        await stop_runtime_process(runtime)

    assert [response.correlation_id for response in responses] == [
        "api-contract-multi-1",
        "api-contract-multi-2",
        "api-contract-multi-3",
    ]
    for response in responses:
        assert response.HasField("output")
        assert response.output.text.strip()


async def _submit_multi_requests(
    port: int,
) -> list[runtime_pb2.SubmitObservationResponse]:
    """Submit three sequential CLI actor_message requests.

    Returns:
        Submitted responses in submission order.
    """
    responses: list[runtime_pb2.SubmitObservationResponse] = []
    for index in range(1, 4):
        response = await submit_observation(
            port=port,
            request=build_cli_submit_observation_request(
                correlation_id=f"api-contract-multi-{index}",
                observation_id=f"api-contract-obs-{index}",
                session_id="api-contract-session",
                external_message_id=f"api-contract-msg-{index}",
                text=f"hello {index}",
            ),
        )
        responses.append(response)
    return responses
