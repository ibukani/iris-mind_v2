"""Delivery config tests."""

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


def test_delivery_enabled_by_default(tmp_path: Path) -> None:
    """Delivery is enabled by default."""
    config = load_runtime_config(None, env={}, cwd=tmp_path)
    assert config.delivery.enabled is True


def test_invalid_delivery_lease_and_attempts_fail(tmp_path: Path) -> None:
    """Invalid delivery lease/max attempts fail validation."""
    path = _write(tmp_path, "[delivery]\nlease_seconds = 0\n")
    with pytest.raises(ConfigError, match=r"delivery\.lease_seconds"):
        load_runtime_config(path, env={})
    path = _write(tmp_path, "[delivery]\nmax_attempts = 0\n")
    with pytest.raises(ConfigError, match=r"delivery\.max_attempts"):
        load_runtime_config(path, env={})


def test_quiet_hours_parse_valid_hhmm(tmp_path: Path) -> None:
    """Valid quiet hours HH:MM values parse."""
    path = _write(
        tmp_path,
        "[delivery.quiet_hours]\nenabled = true\nstart = '21:30'\nend = '07:15'\ntimezone = 'UTC'",
    )
    config = load_runtime_config(path, env={})
    assert config.delivery.quiet_hours.start == "21:30"


def test_invalid_quiet_hours_fail(tmp_path: Path) -> None:
    """Invalid quiet hours values fail."""
    path = _write(tmp_path, "[delivery.quiet_hours]\nstart = '25:00'\n")
    with pytest.raises(ConfigError, match=r"delivery\.quiet_hours\.start"):
        load_runtime_config(path, env={})
