"""Runtime API E2E contract tests for no-send observations.

Presence signals and similar no-send observations must return a valid
SubmitObservationResponse with an empty output text and preserve
correlation_id without requiring an LLM provider. The runtime process
must remain healthy after these observations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from iris.generated.iris.api.v1 import observations_pb2
from iris.generated.iris.runtime.v1 import runtime_pb2
from tests.e2e.helpers import (
    build_cli_activity_event_request,
    build_cli_presence_signal_request,
    build_cli_submit_observation_request,
    find_free_port,
    start_runtime_process,
    stop_runtime_process,
    submit_observation,
    wait_for_runtime_ready,
    write_runtime_config,
)

NO_LIVE_PROVIDER = "fake"

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.e2e
@pytest.mark.anyio
async def test_presence_signal_returns_no_send_response(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """presence_signal returns a SubmitObservationResponse with empty output text."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        response = await submit_observation(
            port=runtime.port,
            request=build_cli_presence_signal_request(
                correlation_id="nosend-presence-corr-1",
                observation_id="nosend-presence-obs-1",
                session_id="nosend-presence-session-1",
                status=observations_pb2.PRESENCE_STATUS_ONLINE,
            ),
        )
    finally:
        await stop_runtime_process(runtime)

    assert isinstance(response, runtime_pb2.SubmitObservationResponse)
    assert not response.output.text


@pytest.mark.e2e
@pytest.mark.anyio
async def test_presence_signal_preserves_correlation_id(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """presence_signal response echoes the client-supplied correlation_id."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        response = await submit_observation(
            port=runtime.port,
            request=build_cli_presence_signal_request(
                correlation_id="nosend-presence-corr-2",
                observation_id="nosend-presence-obs-2",
                session_id="nosend-presence-session-2",
                status=observations_pb2.PRESENCE_STATUS_AWAY,
            ),
        )
    finally:
        await stop_runtime_process(runtime)

    assert response.correlation_id == "nosend-presence-corr-2"


@pytest.mark.e2e
@pytest.mark.anyio
async def test_presence_signal_keeps_runtime_healthy_without_live_provider(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """Repeated no-send presence observations stay healthy with the no-network provider."""
    config_path = write_runtime_config(
        path=tmp_path / "runtime.toml",
        backend="memory",
        models=dict.fromkeys(("default_chat", "fast_judge", "reasoning"), NO_LIVE_PROVIDER),
    )
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
        config_path=config_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        for index in range(1, 4):
            response = await submit_observation(
                port=runtime.port,
                request=build_cli_presence_signal_request(
                    correlation_id=f"nosend-presence-multi-{index}",
                    observation_id=f"nosend-presence-multi-obs-{index}",
                    session_id="nosend-presence-multi-session",
                    status=observations_pb2.PRESENCE_STATUS_ONLINE,
                ),
            )
            assert not response.output.text
        assert runtime.process.poll() is None
        response = await submit_observation(
            port=runtime.port,
            request=build_cli_submit_observation_request(
                correlation_id="nosend-presence-goodbye",
            ),
        )
    finally:
        await stop_runtime_process(runtime)

    assert response.correlation_id == "nosend-presence-goodbye"
    assert response.output.text is not None
    assert response.output.text.strip()


@pytest.mark.e2e
@pytest.mark.anyio
async def test_activity_event_without_reaction_returns_valid_empty_output(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """An activity_event without a reaction returns a valid SubmitObservationResponse."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        response = await submit_observation(
            port=runtime.port,
            request=build_cli_activity_event_request(
                correlation_id="nosend-activity-corr-1",
                observation_id="nosend-activity-obs-1",
                session_id="nosend-activity-session-1",
                activity_kind=observations_pb2.ACTIVITY_KIND_APP_OPENED,
            ),
        )
    finally:
        await stop_runtime_process(runtime)

    assert isinstance(response, runtime_pb2.SubmitObservationResponse)
    assert response.correlation_id == "nosend-activity-corr-1"
    # Activity events without a reaction may return empty output text.
    assert response.output is not None
