"""Stateful runtime process E2E tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import grpc
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
async def test_runtime_process_accepts_multiple_observations_in_same_session(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """Runtime subprocess handles multiple observations in one logical session."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        responses = await _submit_observations(
            runtime.port,
            (
                ("e2e-corr-state-1", "e2e-obs-state-1", "e2e-message-state-1", "hello 1"),
                ("e2e-corr-state-2", "e2e-obs-state-2", "e2e-message-state-2", "hello 2"),
                ("e2e-corr-state-3", "e2e-obs-state-3", "e2e-message-state-3", "hello 3"),
            ),
        )

        assert runtime.is_alive()
    finally:
        await stop_runtime_process(runtime)

    assert [response.correlation_id for response in responses] == [
        "e2e-corr-state-1",
        "e2e-corr-state-2",
        "e2e-corr-state-3",
    ]
    for response in responses:
        assert response.HasField("output")
        assert response.output.text.strip()


@pytest.mark.e2e
@pytest.mark.anyio
async def test_runtime_process_rejects_invalid_observation_without_crashing(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """Runtime subprocess rejects invalid input and remains healthy."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        await _assert_invalid_request_rejected(runtime.port)
        response = await wait_for_runtime_ready(runtime)

        assert response.runtime_name == "iris-mind"
        assert runtime.is_alive()
    finally:
        await stop_runtime_process(runtime)


async def _submit_observations(
    port: int,
    request_specs: tuple[tuple[str, str, str, str], ...],
) -> list[runtime_pb2.SubmitObservationResponse]:
    channel = create_runtime_channel(port)
    try:
        stub = create_runtime_stub(channel)
        responses: list[runtime_pb2.SubmitObservationResponse] = []
        for correlation_id, observation_id, external_message_id, text in request_specs:
            response = await grpc_call(
                stub.SubmitObservation(
                    build_cli_submit_observation_request(
                        correlation_id=correlation_id,
                        observation_id=observation_id,
                        session_id="e2e-stateful-session",
                        external_message_id=external_message_id,
                        text=text,
                    )
                )
            )
            assert isinstance(response, runtime_pb2.SubmitObservationResponse)
            responses.append(response)
        return responses
    finally:
        await channel.close()


async def _assert_invalid_request_rejected(port: int) -> None:
    channel = create_runtime_channel(port)
    try:
        stub = create_runtime_stub(channel)
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await grpc_call(
                stub.SubmitObservation(
                    runtime_pb2.SubmitObservationRequest(correlation_id="invalid-corr-1")
                )
            )

        assert exc_info.value.code() is grpc.StatusCode.INVALID_ARGUMENT
    finally:
        await channel.close()
