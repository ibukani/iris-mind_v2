"""Identity persistence and ephemeral space lifecycle E2E tests."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, cast

import pytest

from iris.adapters.app_gateway.space_resolver import EphemeralSpaceResolver
from iris.adapters.app_gateway.stable_ids import stable_actor_id, stable_space_id
from iris.contracts.external_refs import ExternalSpaceRef
from iris.contracts.spaces import SpaceKind
from iris.core.ids import AccountId, ExternalRef
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
    from collections.abc import Sequence
    from pathlib import Path

    from iris.generated.iris.runtime.v1 import runtime_pb2, runtime_pb2_grpc


@pytest.mark.e2e
@pytest.mark.anyio
async def test_account_persists_across_runtime_restart(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """SQLite state keeps one stable account across runtime restarts."""
    db_path = tmp_path / "state.sqlite3"
    config_path = _write_sqlite_config(tmp_path, db_path)

    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
        config_path=config_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        await _submit_cli_messages(runtime.port, ("msg-1", "msg-2"))
    finally:
        await stop_runtime_process(runtime)

    first_rows = _account_rows(db_path)
    assert len(first_rows) == 1
    first_account_id = first_rows[0]["account_id"]

    restarted = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
        config_path=config_path,
    )
    try:
        await wait_for_runtime_ready(restarted)
        await _submit_cli_messages(restarted.port, ("msg-3",))
    finally:
        await stop_runtime_process(restarted)

    second_rows = _account_rows(db_path)
    assert len(second_rows) == 1
    assert second_rows[0]["account_id"] == first_account_id


@pytest.mark.e2e
@pytest.mark.anyio
async def test_display_name_change_does_not_change_identity(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """display_name update preserves account and provisional actor identity."""
    db_path = tmp_path / "state.sqlite3"
    config_path = _write_sqlite_config(tmp_path, db_path)
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
        config_path=config_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        await _submit_cli_messages(runtime.port, ("msg-1",), display_name="Local User")
        await _submit_cli_messages(runtime.port, ("msg-2",), display_name="Renamed User")
    finally:
        await stop_runtime_process(runtime)

    rows = _account_rows(db_path)
    assert len(rows) == 1
    account_id = AccountId(cast("str", rows[0]["account_id"]))
    assert rows[0]["display_name"] == "Renamed User"
    assert rows[0]["linked_actor_id"] is None
    assert stable_actor_id(account_id) == stable_actor_id(account_id)


@pytest.mark.e2e
@pytest.mark.anyio
async def test_different_provider_creates_different_account(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """Same subject under different providers creates different accounts."""
    db_path = tmp_path / "state.sqlite3"
    config_path = _write_sqlite_config(tmp_path, db_path)
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
        config_path=config_path,
    )
    try:
        await wait_for_runtime_ready(runtime)
        await _submit_cli_messages(runtime.port, ("msg-cli",), provider="cli")
        await _submit_cli_messages(runtime.port, ("msg-discord",), provider="discord")
    finally:
        await stop_runtime_process(runtime)

    rows = _account_rows(db_path)
    assert len(rows) == 2
    account_ids = {row["account_id"] for row in rows}
    actor_ids = {stable_actor_id(AccountId(cast("str", account_id))) for account_id in account_ids}
    assert len(account_ids) == 2
    assert len(actor_ids) == 2


@pytest.mark.e2e
@pytest.mark.anyio
async def test_ephemeral_space_id_is_deterministic_without_persistence() -> None:
    """同じ外部space refは永続storeなしで同じspace_idに解決される。"""
    before_restart = EphemeralSpaceResolver()
    after_restart = EphemeralSpaceResolver()
    first_ref = ExternalSpaceRef(
        provider="cli",
        provider_space_ref=ExternalRef("session:stable-repl-session"),
        display_name="Initial session",
        space_kind=SpaceKind.ROOM,
    )
    second_ref = ExternalSpaceRef(
        provider="cli",
        provider_space_ref=ExternalRef("session:stable-repl-session"),
        display_name="Renamed session",
        space_kind=SpaceKind.THREAD,
    )

    first = await before_restart.resolve_space(first_ref)
    second = await after_restart.resolve_space(second_ref)

    assert first.space_id == second.space_id
    assert first.space_id == stable_space_id(
        "cli",
        ExternalRef("session:stable-repl-session"),
    )


def _write_sqlite_config(tmp_path: Path, db_path: Path) -> Path:
    config_path = tmp_path / "runtime.toml"
    config_path.write_text(
        f"""
[state]
backend = "sqlite"
sqlite_path = "{db_path}"
""",
        encoding="utf-8",
    )
    return config_path


async def _submit_cli_messages(
    port: int,
    message_ids: Sequence[str],
    *,
    provider: str = "cli",
    display_name: str = "Local User",
) -> None:
    channel = create_runtime_channel(port)
    try:
        stub = create_runtime_stub(channel)
        for index, message_id in enumerate(message_ids, start=1):
            await _submit_identity_message(
                stub=stub,
                provider=provider,
                display_name=display_name,
                message_id=message_id,
                text=f"hello {index}",
            )
    finally:
        await channel.close()


async def _submit_identity_message(
    *,
    stub: runtime_pb2_grpc.IrisRuntimeServiceStub,
    provider: str,
    display_name: str,
    message_id: str,
    text: str,
) -> None:
    request = build_cli_submit_observation_request(
        correlation_id=f"corr-{message_id}",
        observation_id=f"obs-{message_id}",
        session_id="identity-space-session",
        external_message_id=message_id,
        text=text,
    )
    request.observation.context.account_ref.provider = provider
    request.observation.context.account_ref.provider_subject = "user-1"
    request.observation.context.account_ref.display_name = display_name
    request.observation.context.space_ref.provider = provider
    request.observation.context.space_ref.provider_space_ref = "space-1"
    response = await grpc_call(stub.SubmitObservation(request))
    typed_response = cast("runtime_pb2.SubmitObservationResponse", response)
    assert typed_response.output.text.strip()


def _account_rows(db_path: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM accounts ORDER BY provider, provider_subject").fetchall()
        return list(rows)
    finally:
        conn.close()
