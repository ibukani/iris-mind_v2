"""Strict safety config tests。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.runtime.config import load_runtime_config

if TYPE_CHECKING:
    from pathlib import Path


def test_strict_safety_mode_from_toml(tmp_path: Path) -> None:
    """Strict mode は TOML から読み込める。"""
    path = tmp_path / "runtime.toml"
    path.write_text("[safety]\nmode = 'strict'\n", encoding="utf-8")
    assert load_runtime_config(path, env={}).safety.mode == "strict"


def test_strict_safety_mode_from_env() -> None:
    """Strict mode は env override から読み込める。"""
    config = load_runtime_config(None, env={"IRIS_SAFETY_MODE": "strict"})
    assert config.safety.mode == "strict"
