"""Interaction activity runtime config tests。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from iris.runtime.config import ConfigError, load_runtime_config
from tests.helpers.approx import approx

if TYPE_CHECKING:
    from pathlib import Path


def test_interaction_activity_projection_is_disabled_by_default(tmp_path: Path) -> None:
    """Projection利用は明示有効化までoff。"""
    config = load_runtime_config(None, env={}, cwd=tmp_path)

    assert config.interaction_activity.enabled is False
    assert config.interaction_activity.max_ttl_seconds == approx(300.0)


def test_interaction_activity_projection_config_loads_from_toml(tmp_path: Path) -> None:
    """Projection gateとserver TTLをtyped configから読む。"""
    path = tmp_path / "runtime.toml"
    path.write_text(
        "[interaction_activity]\nenabled = true\nmax_ttl_seconds = 90.0\n",
        encoding="utf-8",
    )

    config = load_runtime_config(path, env={})

    assert config.interaction_activity.enabled is True
    assert config.interaction_activity.max_ttl_seconds == approx(90.0)


def test_interaction_activity_rejects_non_positive_ttl(tmp_path: Path) -> None:
    """Indefinite/無効TTLをruntime configで拒否する。"""
    path = tmp_path / "runtime.toml"
    path.write_text("[interaction_activity]\nmax_ttl_seconds = 0\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="max_ttl_seconds must be greater than zero"):
        load_runtime_config(path, env={})
