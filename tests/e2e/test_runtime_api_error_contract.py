"""Runtime API E2E contract tests for SubmitObservation error responses.

The gRPC contract must reject malformed requests as INVALID_ARGUMENT without
crashing the runtime. The runtime process must stay healthy after each
rejection so subsequent requests still succeed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from iris.adapters.grpc.mappers import timestamp_from_datetime
from iris.generated.iris.api.v1 import observations_pb2
from iris.generated.iris.runtime.v1 import runtime_pb2
from tests.e2e.helpers import (
    assert_invalid_request,
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


_OCCURRED_AT = datetime(2026, 6, 14, 12, 0, tzinfo=UTC)


@pytest.mark.e2e
@pytest.mark.anyio
async def test_missing_observation_returns_invalid_argument_and_keeps_server_alive(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """A SubmitObservationRequest without observation returns INVALID_ARGUMENT."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        await assert_invalid_request(
            runtime.port,
            runtime_pb2.SubmitObservationRequest(correlation_id="missing-obs-1"),
        )
        response = await get_runtime_info(runtime.port)
        assert response.runtime_name == "iris-mind"
        assert runtime.is_alive()
    finally:
        await stop_runtime_process(runtime)


@pytest.mark.e2e
@pytest.mark.anyio
async def test_unspecified_observation_kind_returns_invalid_argument(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """OBSERVATION_KIND_UNSPECIFIED is rejected as INVALID_ARGUMENT."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        request = runtime_pb2.SubmitObservationRequest(
            correlation_id="unspec-kind-1",
            observation=observations_pb2.Observation(
                observation_id="unspec-obs-1",
                session_id="unspec-session-1",
                kind=observations_pb2.OBSERVATION_KIND_UNSPECIFIED,
                occurred_at=timestamp_from_datetime(_OCCURRED_AT),
            ),
        )
        await assert_invalid_request(runtime.port, request)
    finally:
        await stop_runtime_process(runtime)


@pytest.mark.e2e
@pytest.mark.anyio
async def test_kind_payload_mismatch_returns_invalid_argument(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """A kind/payload oneof mismatch is rejected as INVALID_ARGUMENT."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        request = runtime_pb2.SubmitObservationRequest(
            correlation_id="kind-mismatch-1",
            observation=observations_pb2.Observation(
                observation_id="kind-mismatch-obs-1",
                session_id="kind-mismatch-session-1",
                kind=observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE,
                occurred_at=timestamp_from_datetime(_OCCURRED_AT),
                idle_tick=observations_pb2.IdleTickPayload(
                    reason="mismatch",
                    idle_seconds=0.0,
                ),
            ),
        )
        await assert_invalid_request(runtime.port, request)
    finally:
        await stop_runtime_process(runtime)


@pytest.mark.e2e
@pytest.mark.anyio
async def test_runtime_recovers_after_invalid_request(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """After a rejection the runtime still serves a healthy GetRuntimeInfo and a good request."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        await assert_invalid_request(
            runtime.port,
            runtime_pb2.SubmitObservationRequest(correlation_id="recover-1"),
        )
        response = await submit_observation(
            port=runtime.port,
            request=build_cli_submit_observation_request(
                correlation_id="recover-good-1",
            ),
        )
    finally:
        await stop_runtime_process(runtime)

    assert response.correlation_id == "recover-good-1"
    assert response.output.text is not None
    assert response.output.text.strip()


@pytest.mark.e2e
@pytest.mark.anyio
async def test_missing_occurred_at_returns_invalid_argument(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """An observation without occurred_at is rejected as INVALID_ARGUMENT."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        request = runtime_pb2.SubmitObservationRequest(
            correlation_id="missing-occurred-at-1",
            observation=observations_pb2.Observation(
                observation_id="missing-occurred-at-obs-1",
                session_id="missing-occurred-at-session-1",
                kind=observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE,
                actor_message=observations_pb2.ActorMessagePayload(
                    text="hello",
                ),
            ),
        )
        await assert_invalid_request(runtime.port, request)
    finally:
        await stop_runtime_process(runtime)


@pytest.mark.e2e
@pytest.mark.anyio
async def test_missing_account_ref_provider_returns_invalid_argument(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """An account_ref without provider is rejected as INVALID_ARGUMENT."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        request = build_cli_submit_observation_request(
            correlation_id="missing-account-provider-1",
        )
        request.observation.context.account_ref.provider = ""
        await assert_invalid_request(runtime.port, request)
    finally:
        await stop_runtime_process(runtime)


@pytest.mark.e2e
@pytest.mark.anyio
async def test_missing_account_ref_provider_subject_returns_invalid_argument(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """An account_ref without provider_subject is rejected as INVALID_ARGUMENT."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        request = build_cli_submit_observation_request(
            correlation_id="missing-account-subject-1",
        )
        request.observation.context.account_ref.provider_subject = ""
        await assert_invalid_request(runtime.port, request)
    finally:
        await stop_runtime_process(runtime)


@pytest.mark.e2e
@pytest.mark.anyio
async def test_missing_account_ref_display_name_returns_invalid_argument(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """An account_ref without display_name is rejected as INVALID_ARGUMENT."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        request = build_cli_submit_observation_request(
            correlation_id="missing-account-display-1",
        )
        request.observation.context.account_ref.display_name = ""
        await assert_invalid_request(runtime.port, request)
    finally:
        await stop_runtime_process(runtime)


@pytest.mark.e2e
@pytest.mark.anyio
async def test_missing_space_ref_provider_returns_invalid_argument(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """A space_ref without provider is rejected as INVALID_ARGUMENT."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        request = build_cli_submit_observation_request(
            correlation_id="missing-space-provider-1",
        )
        request.observation.context.space_ref.provider = ""
        await assert_invalid_request(runtime.port, request)
    finally:
        await stop_runtime_process(runtime)


@pytest.mark.e2e
@pytest.mark.anyio
async def test_missing_space_ref_provider_space_ref_returns_invalid_argument(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """A space_ref without provider_space_ref is rejected as INVALID_ARGUMENT."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        request = build_cli_submit_observation_request(
            correlation_id="missing-space-ref-1",
        )
        request.observation.context.space_ref.provider_space_ref = ""
        await assert_invalid_request(runtime.port, request)
    finally:
        await stop_runtime_process(runtime)


@pytest.mark.e2e
@pytest.mark.anyio
async def test_missing_space_ref_display_name_returns_invalid_argument(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """A space_ref without display_name is rejected as INVALID_ARGUMENT."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        request = build_cli_submit_observation_request(
            correlation_id="missing-space-display-1",
        )
        request.observation.context.space_ref.display_name = ""
        await assert_invalid_request(runtime.port, request)
    finally:
        await stop_runtime_process(runtime)
