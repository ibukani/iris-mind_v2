"""LLM プロバイダ診断のランタイム設定検証。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from iris.runtime.config import (
    ConfigError,
    RuntimeDiagnosticsConfig,
    default_runtime_config,
    load_runtime_config,
)
from tests.helpers.approx import approx

if TYPE_CHECKING:
    from pathlib import Path


def test_default_diagnostics_config() -> None:
    """デフォルト診断設定の値が想定通り。"""
    config = default_runtime_config()

    assert config.diagnostics == RuntimeDiagnosticsConfig()
    assert config.diagnostics.enabled is True
    assert config.diagnostics.timeout_seconds == approx(5.0)
    assert config.diagnostics.fail_fast is False
    assert config.diagnostics.warmup_models is False
    assert config.diagnostics.log_issues_as_warnings is True


def test_diagnostics_toml_is_applied(tmp_path: Path) -> None:
    """Diagnostics sectionはTOMLからtyped configへ適用される。"""
    config = load_runtime_config(
        _write(
            tmp_path,
            (
                "[diagnostics]\n"
                "enabled = false\n"
                "timeout_seconds = 2.5\n"
                "fail_fast = true\n"
                "warmup_models = true\n"
                "log_issues_as_warnings = false\n"
            ),
        ),
        env={},
    )

    assert config.diagnostics.enabled is False
    assert config.diagnostics.timeout_seconds == approx(2.5)
    assert config.diagnostics.fail_fast is True
    assert config.diagnostics.warmup_models is True
    assert config.diagnostics.log_issues_as_warnings is False


def test_diagnostics_toml_partial_override_preserves_defaults(
    tmp_path: Path,
) -> None:
    """Diagnostics sectionの一部key省略はデフォルトを保持する。"""
    config = load_runtime_config(
        _write(tmp_path, "[diagnostics]\ntimeout_seconds = 10.0\n"),
        env={},
    )

    assert config.diagnostics.timeout_seconds == approx(10.0)
    assert config.diagnostics.enabled is True
    assert config.diagnostics.fail_fast is False
    assert config.diagnostics.warmup_models is False
    assert config.diagnostics.log_issues_as_warnings is True


def test_diagnostics_env_overrides_toml(tmp_path: Path) -> None:
    """Diagnostics環境変数はTOML値より優先される。"""
    config = load_runtime_config(
        _write(
            tmp_path,
            ("[diagnostics]\nenabled = true\ntimeout_seconds = 5.0\nfail_fast = false\n"),
        ),
        env={
            "IRIS_DIAGNOSTICS_ENABLED": "false",
            "IRIS_DIAGNOSTICS_TIMEOUT_SECONDS": "12.5",
            "IRIS_DIAGNOSTICS_FAIL_FAST": "true",
        },
    )

    assert config.diagnostics.enabled is False
    assert config.diagnostics.timeout_seconds == approx(12.5)
    assert config.diagnostics.fail_fast is True


def test_diagnostics_env_accepts_common_bool_forms() -> None:
    """Diagnostics環境変数の真偽値は典型的な文字列を受理する。"""
    for raw, expected in (
        ("true", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("false", False),
        ("0", False),
        ("no", False),
        ("off", False),
    ):
        config = load_runtime_config(
            None,
            env={"IRIS_DIAGNOSTICS_ENABLED": raw},
        )
        assert config.diagnostics.enabled is expected, raw


def test_diagnostics_env_rejects_invalid_bool() -> None:
    """Diagnostics環境変数の真偽値として解釈できない値はConfigError。"""
    with pytest.raises(ConfigError, match="IRIS_DIAGNOSTICS_ENABLED"):
        load_runtime_config(
            None,
            env={"IRIS_DIAGNOSTICS_ENABLED": "maybe"},
        )


def test_diagnostics_timeout_must_be_positive(tmp_path: Path) -> None:
    """Diagnostics timeout_secondsは正の値でなければならない。"""
    with pytest.raises(
        ConfigError,
        match=r"diagnostics\.timeout_seconds must be greater than zero",
    ):
        load_runtime_config(
            _write(tmp_path, "[diagnostics]\ntimeout_seconds = 0.0\n"),
            env={},
        )


def test_diagnostics_enabled_must_be_bool(tmp_path: Path) -> None:
    """Diagnostics enabledは真偽値でなければならない。"""
    with pytest.raises(ConfigError, match=r"diagnostics\.enabled.*boolean"):
        load_runtime_config(
            _write(tmp_path, '[diagnostics]\nenabled = "yes"\n'),
            env={},
        )


def test_diagnostics_unknown_key_is_rejected(tmp_path: Path) -> None:
    """Diagnostics sectionの未知keyはConfigError。"""
    with pytest.raises(ConfigError, match=r"diagnostics\.unexpected"):
        load_runtime_config(
            _write(tmp_path, "[diagnostics]\nunexpected = 1\n"),
            env={},
        )


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "runtime.toml"
    path.write_text(content, encoding="utf-8")
    return path
