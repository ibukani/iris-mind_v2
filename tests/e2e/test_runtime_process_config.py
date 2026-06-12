"""Runtime process configuration E2E tests."""

from __future__ import annotations

import subprocess  # noqa: S404 -- E2E test handles a fixed local runtime subprocess.
from typing import TYPE_CHECKING

import pytest

from tests.e2e.helpers import (
    find_free_port,
    start_runtime_process,
    stop_runtime_process,
    wait_for_runtime_ready,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.e2e
@pytest.mark.anyio
async def test_runtime_process_starts_without_config_file(tmp_path: Path, repo_root: Path) -> None:
    """Runtime subprocess starts with built-in defaults and no config file."""
    config_path = tmp_path / ".iris/config/runtime.toml"
    assert not config_path.exists()

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


@pytest.mark.e2e
def test_runtime_process_fails_with_missing_explicit_config(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """Runtime subprocess fails clearly for an explicit missing config path."""
    runtime = start_runtime_process(
        port=find_free_port(),
        repo_root=repo_root,
        runtime_home=tmp_path,
        config_path=tmp_path / "missing.toml",
    )
    stdout, stderr = _communicate_or_kill(runtime.process)
    runtime.stdout = stdout
    runtime.stderr = stderr
    output = f"{stdout}\n{stderr}".lower()

    assert runtime.process.returncode is not None
    assert runtime.process.returncode != 0
    assert any(token in output for token in ("configerror", "config", "not found", "missing"))


def _communicate_or_kill(process: subprocess.Popen[str]) -> tuple[str, str]:
    try:
        return process.communicate(timeout=5.0)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.communicate()
