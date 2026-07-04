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


def test_strict_safety_mode_from_env(tmp_path: Path) -> None:
    """Strict mode は env override から読み込める。"""
    config = load_runtime_config(
        None,
        env={"IRIS_SAFETY_MODE": "strict"},
        cwd=tmp_path,
    )
    assert config.safety.mode == "strict"


def test_high_risk_context_detection_defaults_off(tmp_path: Path) -> None:
    """High-risk context detection は明示設定なしでは無効。"""
    config = load_runtime_config(None, env={}, cwd=tmp_path)

    assert config.safety.high_risk_context_detection_enabled is False


def test_high_risk_context_detection_from_toml(tmp_path: Path) -> None:
    """High-risk context detection は TOML から有効化できる。"""
    path = tmp_path / "runtime.toml"
    path.write_text(
        "[safety]\nhigh_risk_context_detection_enabled = true\n",
        encoding="utf-8",
    )

    assert load_runtime_config(path, env={}).safety.high_risk_context_detection_enabled is True


def test_high_risk_context_detection_from_env(tmp_path: Path) -> None:
    """High-risk context detection は env override から有効化できる。"""
    config = load_runtime_config(
        None,
        env={"IRIS_SAFETY_HIGH_RISK_CONTEXT_DETECTION_ENABLED": "true"},
        cwd=tmp_path,
    )

    assert config.safety.high_risk_context_detection_enabled is True
