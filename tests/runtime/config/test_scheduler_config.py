"""Scheduler config tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from iris.runtime.config import ConfigError, load_runtime_config

if TYPE_CHECKING:
    from pathlib import Path


def _write(tmp_path: Path, text: str) -> Path:
    """Write a runtime config file.

    Returns:
        書き込んだ設定ファイルパス。
    """
    path = tmp_path / "runtime.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_scheduler_disabled_by_default() -> None:
    """Scheduler is disabled by default."""
    config = load_runtime_config(None, env={})
    assert config.scheduler.enabled is False


def test_invalid_scheduler_intervals_fail(tmp_path: Path) -> None:
    """Invalid scheduler numeric bounds fail validation."""
    path = _write(tmp_path, "[scheduler]\ninterval_seconds = 0\n")
    with pytest.raises(ConfigError, match=r"scheduler\.interval_seconds"):
        load_runtime_config(path, env={})


def test_scheduler_toml_values_parse(tmp_path: Path) -> None:
    """Scheduler TOML values are parsed."""
    path = _write(
        tmp_path,
        """\
[scheduler]
enabled = true
interval_seconds = 10
idle_threshold_seconds = 20
min_interval_per_target_seconds = 30
max_due_per_run = 2
""",
    )
    config = load_runtime_config(path, env={})
    assert config.scheduler.enabled is True
    assert config.scheduler.max_due_per_run == 2
