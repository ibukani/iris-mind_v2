"""Runtime API E2E contract tests for ExternalAccountRef identity resolution.

These tests assert the gRPC contract for identity-bearing SubmitObservation
requests: stable account persistence, display_name as display-only,
provider-scoped identity, and INVALID_ARGUMENT for invalid context shapes.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest

from iris.adapters.app_gateway.stable_ids import stable_actor_id
from iris.core.ids import AccountId
from tests.e2e.helpers import (
    assert_invalid_request,
    build_cli_submit_observation_request,
    find_free_port,
    start_runtime_process,
    stop_runtime_process,
    submit_observation,
    wait_for_runtime_ready,
    write_runtime_config,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from iris.generated.iris.runtime.v1 import runtime_pb2


@pytest.mark.e2e
@pytest.mark.anyio
async def test_account_ref_persists_across_runtime_restart(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """A stable account_ref produces a single account_id across runtime restarts."""
    db_path = tmp_path / "state.sqlite3"
    config_path = write_runtime_config(
        path=tmp_path / "runtime.toml",
        backend="sqlite",
        sqlite_path=db_path,
    )

    first = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
        config_path=config_path,
    )
    try:
        await wait_for_runtime_ready(first)
        await _submit_identity_messages(first.port, ("id-corr-1", "id-corr-2"))
    finally:
        await stop_runtime_process(first)

    first_account_id = _single_account_id(db_path)

    second = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
        config_path=config_path,
    )
    try:
        await wait_for_runtime_ready(second)
        await _submit_identity_messages(second.port, ("id-corr-3",))
    finally:
        await stop_runtime_process(second)

    second_account_id = _single_account_id(db_path)
    assert second_account_id == first_account_id


@pytest.mark.e2e
@pytest.mark.anyio
async def test_display_name_change_does_not_create_new_account(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """Changing display_name updates the same account rather than creating a new one."""
    db_path = tmp_path / "state.sqlite3"
    config_path = write_runtime_config(
        path=tmp_path / "runtime.toml",
        backend="sqlite",
        sqlite_path=db_path,
    )
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
        config_path=config_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        await _submit_identity_messages(
            runtime.port,
            ("display-corr-1",),
            display_name="Local User",
        )
        first_account_id = _single_account_id(db_path)
        await _submit_identity_messages(
            runtime.port,
            ("display-corr-2",),
            display_name="Renamed User",
        )
    finally:
        await stop_runtime_process(runtime)

    rows = _account_rows(db_path)
    assert len(rows) == 1
    assert rows[0]["account_id"] == first_account_id
    assert rows[0]["display_name"] == "Renamed User"
    assert rows[0]["linked_actor_id"] is None
    assert stable_actor_id(first_account_id) == stable_actor_id(AccountId(rows[0]["account_id"]))


@pytest.mark.e2e
@pytest.mark.anyio
async def test_same_provider_subject_under_different_providers_creates_distinct_accounts(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """Same provider_subject under different providers maps to different accounts."""
    db_path = tmp_path / "state.sqlite3"
    config_path = write_runtime_config(
        path=tmp_path / "runtime.toml",
        backend="sqlite",
        sqlite_path=db_path,
    )
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
        config_path=config_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        await _submit_identity_messages(
            runtime.port,
            ("provider-corr-cli",),
            provider="cli",
        )
        await _submit_identity_messages(
            runtime.port,
            ("provider-corr-discord",),
            provider="discord",
        )
    finally:
        await stop_runtime_process(runtime)

    rows = _account_rows(db_path)
    assert len(rows) == 2
    account_ids = {row["account_id"] for row in rows}
    actor_ids = {stable_actor_id(AccountId(row["account_id"])) for row in rows}
    assert len(account_ids) == 2
    assert len(actor_ids) == 2


@pytest.mark.e2e
@pytest.mark.anyio
async def test_account_ref_with_account_id_is_invalid_argument(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """account_ref and account_id set together is rejected as INVALID_ARGUMENT."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        await assert_invalid_request(
            runtime.port,
            _request_with_account_ref_and_account_id(),
        )
    finally:
        await stop_runtime_process(runtime)


async def _submit_identity_messages(
    port: int,
    correlation_ids: Sequence[str],
    *,
    provider: str = "cli",
    display_name: str = "Local User",
) -> None:
    """Submit a sequence of identity-bearing actor_message requests."""
    for index, correlation_id in enumerate(correlation_ids, start=1):
        request = build_cli_submit_observation_request(
            correlation_id=correlation_id,
            observation_id=f"id-obs-{correlation_id}",
            session_id="identity-contract-session",
            external_message_id=f"id-msg-{correlation_id}",
            text=f"identity {index}",
        )
        request.observation.context.account_ref.provider = provider
        request.observation.context.account_ref.provider_subject = "subject-1"
        request.observation.context.account_ref.display_name = display_name
        await submit_observation(port=port, request=request)


def _request_with_account_ref_and_account_id() -> runtime_pb2.SubmitObservationRequest:
    """Return a request with both account_ref and account_id set.

    Returns:
        Request with conflicting identity fields.
    """
    request = build_cli_submit_observation_request(correlation_id="bad-id-corr-1")
    request.observation.context.account_id = "should-not-be-set"
    return request


def _account_rows(db_path: Path) -> list[sqlite3.Row]:
    """Read all rows from the accounts table ordered by provider and subject.

    Returns:
        Account rows from sqlite.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM accounts ORDER BY provider, provider_subject").fetchall()
        return list(rows)
    finally:
        conn.close()


def _single_account_id(db_path: Path) -> AccountId:
    """Assert exactly one account exists and return its account_id.

    Returns:
        AccountId of the single row.
    """
    rows = _account_rows(db_path)
    assert len(rows) == 1
    raw_id = rows[0]["account_id"]
    assert isinstance(raw_id, str)
    return AccountId(raw_id)
