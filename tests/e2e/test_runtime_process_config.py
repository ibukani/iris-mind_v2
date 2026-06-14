"""Runtime process configuration E2E tests."""

from __future__ import annotations

import asyncio
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

    from tests.e2e.runtime_process import RuntimeProcess


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
    stdout, stderr = _communicate_or_kill(runtime)
    output = f"{stdout}\n{stderr}".lower()

    assert runtime.returncode is not None
    assert runtime.returncode != 0
    assert any(token in output for token in ("configerror", "config", "not found", "missing"))


def _communicate_or_kill(runtime: RuntimeProcess) -> tuple[str, str]:
    """Stop a runtime subprocess and return captured output.

    Returns:
        Captured ``stdout`` and ``stderr``.
    """
    return asyncio.run(runtime.stop())
