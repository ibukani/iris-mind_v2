"""Runtime API E2E contract tests for ExternalSpaceRef resolution.

The default server resolves ExternalSpaceRef ephemerally and deterministically
and does not persist SpaceBinding. These tests lock the external contract
without depending on internal state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import grpc
import pytest

from iris.adapters.app_gateway.space_resolver import EphemeralSpaceResolver
from iris.adapters.app_gateway.stable_ids import stable_space_id
from iris.contracts.external_refs import ExternalSpaceRef
from iris.contracts.spaces import SpaceKind
from iris.core.ids import ExternalRef
from iris.generated.iris.api.v1 import spaces_pb2
from tests.e2e.helpers import (
    build_cli_submit_observation_request,
    create_runtime_channel,
    create_runtime_stub,
    find_free_port,
    start_runtime_process,
    stop_runtime_process,
    submit_observation,
    wait_for_runtime_ready,
)
from tests.helpers.grpc_test import grpc_call

if TYPE_CHECKING:
    from pathlib import Path

    from iris.generated.iris.runtime.v1 import runtime_pb2


@pytest.mark.e2e
@pytest.mark.anyio
async def test_space_ref_resolves_to_deterministic_space_id() -> None:
    """The same ExternalSpaceRef maps to the same space_id across resolver invocations."""
    before_resolver = EphemeralSpaceResolver()
    after_resolver = EphemeralSpaceResolver()
    space_ref = ExternalSpaceRef(
        provider="cli",
        provider_space_ref=ExternalRef("session:stable-repl"),
        display_name="Initial session",
        space_kind=SpaceKind.ROOM,
    )
    before_space = await before_resolver.resolve_space(space_ref)
    after_space = await after_resolver.resolve_space(space_ref)
    expected_space_id = stable_space_id("cli", ExternalRef("session:stable-repl"))

    assert before_space.space_id == after_space.space_id == expected_space_id


@pytest.mark.e2e
@pytest.mark.anyio
async def test_display_name_and_space_kind_does_not_change_space_id() -> None:
    """display_name and space_kind changes do not affect the deterministic space_id."""
    resolver = EphemeralSpaceResolver()
    first_ref = ExternalSpaceRef(
        provider="cli",
        provider_space_ref=ExternalRef("session:space-shape-1"),
        display_name="Original name",
        space_kind=SpaceKind.ROOM,
    )
    second_ref = ExternalSpaceRef(
        provider="cli",
        provider_space_ref=ExternalRef("session:space-shape-1"),
        display_name="Renamed room",
        space_kind=SpaceKind.THREAD,
    )
    first_space = await resolver.resolve_space(first_ref)
    second_space = await resolver.resolve_space(second_ref)

    assert first_space.space_id == second_space.space_id


@pytest.mark.e2e
@pytest.mark.anyio
async def test_default_runtime_does_not_persist_space_bindings(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """A default backend=memory runtime does not create or store SpaceBinding rows."""
    db_path = tmp_path / "state.sqlite3"
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        await _submit_space_observations(runtime.port, ("space-corr-1", "space-corr-2"))
    finally:
        await stop_runtime_process(runtime)

    assert not db_path.exists(), "default in-memory runtime must not create a sqlite database file"


@pytest.mark.e2e
@pytest.mark.anyio
async def test_space_ref_with_space_id_is_invalid_argument(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """Setting both space_ref and space_id is rejected as INVALID_ARGUMENT."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        request = build_cli_submit_observation_request(correlation_id="bad-space-corr-1")
        request.observation.context.space_id = "should-not-be-set"
        await _assert_invalid_request(runtime.port, request)
    finally:
        await stop_runtime_process(runtime)


@pytest.mark.e2e
@pytest.mark.anyio
async def test_space_ref_with_unspecified_space_kind_is_invalid_argument(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """An ExternalSpaceRef with SPACE_KIND_UNSPECIFIED is rejected as INVALID_ARGUMENT."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        request = build_cli_submit_observation_request(correlation_id="bad-space-kind-corr")
        request.observation.context.space_ref.space_kind = spaces_pb2.SPACE_KIND_UNSPECIFIED
        await _assert_invalid_request(runtime.port, request)
    finally:
        await stop_runtime_process(runtime)


async def _submit_space_observations(
    port: int,
    correlation_ids: tuple[str, ...],
) -> None:
    """Submit actor_message requests that exercise ExternalSpaceRef resolution."""
    for index, correlation_id in enumerate(correlation_ids, start=1):
        await submit_observation(
            port=port,
            request=build_cli_submit_observation_request(
                correlation_id=correlation_id,
                observation_id=f"space-obs-{correlation_id}",
                session_id="space-contract-session",
                external_message_id=f"space-msg-{correlation_id}",
                text=f"space {index}",
            ),
        )


async def _assert_invalid_request(
    port: int,
    request: runtime_pb2.SubmitObservationRequest,
) -> None:
    """Assert that a request fails with INVALID_ARGUMENT."""
    channel = create_runtime_channel(port)
    try:
        stub = create_runtime_stub(channel)
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await grpc_call(stub.SubmitObservation(request))
    finally:
        await channel.close()
    assert exc_info.value.code() is grpc.StatusCode.INVALID_ARGUMENT
