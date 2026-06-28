"""LLM プロバイダ診断のランタイム設定検証。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from iris.runtime.config import (
    ConfigError,
    DiagnosticsMode,
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
    assert config.diagnostics.mode == DiagnosticsMode.WARN
    assert config.diagnostics.timeout_seconds == approx(5.0)
    assert config.diagnostics.readiness_timeout_seconds == approx(5.0)
    assert config.diagnostics.warmup_timeout_seconds == approx(120.0)
    assert config.diagnostics.warmup_models is False


def test_diagnostics_toml_is_applied(tmp_path: Path) -> None:
    """Diagnostics sectionはTOMLからtyped configへ適用される。"""
    config = load_runtime_config(
        _write(
            tmp_path,
            ('[diagnostics]\nmode = "strict"\ntimeout_seconds = 2.5\nwarmup_models = true\n'),
        ),
        env={},
    )

    assert config.diagnostics.mode == DiagnosticsMode.STRICT
    assert config.diagnostics.timeout_seconds == approx(2.5)
    assert config.diagnostics.warmup_models is True


def test_diagnostics_toml_partial_override_preserves_defaults(
    tmp_path: Path,
) -> None:
    """Diagnostics sectionの一部key省略はデフォルトを保持する。"""
    config = load_runtime_config(
        _write(tmp_path, "[diagnostics]\ntimeout_seconds = 10.0\n"),
        env={},
    )

    assert config.diagnostics.timeout_seconds == approx(10.0)
    assert config.diagnostics.mode == DiagnosticsMode.WARN
    assert config.diagnostics.warmup_models is False


def test_diagnostics_env_overrides_toml(tmp_path: Path) -> None:
    """Diagnostics環境変数はTOML値より優先される。"""
    config = load_runtime_config(
        _write(
            tmp_path,
            ('[diagnostics]\nmode = "warn"\ntimeout_seconds = 5.0\n'),
        ),
        env={
            "IRIS_DIAGNOSTICS_MODE": "strict",
            "IRIS_DIAGNOSTICS_TIMEOUT_SECONDS": "12.5",
            "IRIS_DIAGNOSTICS_WARMUP_MODELS": "true",
        },
    )

    assert config.diagnostics.mode == DiagnosticsMode.STRICT
    assert config.diagnostics.timeout_seconds == approx(12.5)
    assert config.diagnostics.warmup_models is True


def test_diagnostics_mode_off_via_env() -> None:
    """Diagnostics環境変数でmode=offを指定できる。"""
    config = load_runtime_config(
        None,
        env={"IRIS_DIAGNOSTICS_MODE": "off"},
    )
    assert config.diagnostics.mode == DiagnosticsMode.OFF


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
            env={"IRIS_DIAGNOSTICS_WARMUP_MODELS": raw},
        )
        assert config.diagnostics.warmup_models is expected, raw


def test_diagnostics_env_rejects_invalid_bool() -> None:
    """Diagnostics環境変数の真偽値として解釈できない値はConfigError。"""
    with pytest.raises(ConfigError, match="IRIS_DIAGNOSTICS_WARMUP_MODELS"):
        load_runtime_config(
            None,
            env={"IRIS_DIAGNOSTICS_WARMUP_MODELS": "maybe"},
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


def test_diagnostics_warmup_models_must_be_bool(tmp_path: Path) -> None:
    """Diagnostics warmup_modelsは真偽値でなければならない。"""
    with pytest.raises(ConfigError, match=r"diagnostics\.warmup_models.*boolean"):
        load_runtime_config(
            _write(tmp_path, '[diagnostics]\nwarmup_models = "yes"\n'),
            env={},
        )


def test_diagnostics_mode_must_be_valid(tmp_path: Path) -> None:
    """Diagnostics modeは ``off``/``warn``/``strict`` のいずれかでなければならない。"""
    with pytest.raises(ConfigError, match=r"diagnostics\.mode"):
        load_runtime_config(
            _write(tmp_path, '[diagnostics]\nmode = "invalid"\n'),
            env={},
        )


def test_diagnostics_unknown_key_is_rejected(tmp_path: Path) -> None:
    """Diagnostics sectionの未知keyはConfigError。"""
    with pytest.raises(ConfigError, match=r"diagnostics\.unexpected"):
        load_runtime_config(
            _write(tmp_path, "[diagnostics]\nunexpected = 1\n"),
            env={},
        )


def test_diagnostics_toml_legacy_timeout_sets_both(tmp_path: Path) -> None:
    """Legacy timeout_seconds TOML setting configures both timeouts."""
    config = load_runtime_config(
        _write(tmp_path, "[diagnostics]\ntimeout_seconds = 60.0\n"),
        env={},
    )
    assert config.diagnostics.timeout_seconds == approx(60.0)
    assert config.diagnostics.readiness_timeout_seconds == approx(60.0)
    assert config.diagnostics.warmup_timeout_seconds == approx(60.0)


def test_diagnostics_toml_stage_specific_timeouts(tmp_path: Path) -> None:
    """Stage specific timeout TOML settings override defaults."""
    config = load_runtime_config(
        _write(
            tmp_path,
            "[diagnostics]\nreadiness_timeout_seconds = 2.0\nwarmup_timeout_seconds = 300.0\n",
        ),
        env={},
    )
    assert config.diagnostics.readiness_timeout_seconds == approx(2.0)
    assert config.diagnostics.warmup_timeout_seconds == approx(300.0)


def test_diagnostics_env_legacy_timeout_sets_both() -> None:
    """Legacy timeout_seconds ENV setting configures both timeouts."""
    config = load_runtime_config(
        None,
        env={"IRIS_DIAGNOSTICS_TIMEOUT_SECONDS": "60.0"},
    )
    assert config.diagnostics.timeout_seconds == approx(60.0)
    assert config.diagnostics.readiness_timeout_seconds == approx(60.0)
    assert config.diagnostics.warmup_timeout_seconds == approx(60.0)


def test_diagnostics_env_stage_specific_timeouts() -> None:
    """Stage specific timeout ENV settings override defaults."""
    config = load_runtime_config(
        None,
        env={
            "IRIS_DIAGNOSTICS_READINESS_TIMEOUT_SECONDS": "2.0",
            "IRIS_DIAGNOSTICS_WARMUP_TIMEOUT_SECONDS": "300.0",
        },
    )
    assert config.diagnostics.readiness_timeout_seconds == approx(2.0)
    assert config.diagnostics.warmup_timeout_seconds == approx(300.0)


def test_diagnostics_timeout_must_be_positive_all(tmp_path: Path) -> None:
    """Stage specific timeouts must be positive."""
    with pytest.raises(
        ConfigError, match=r"diagnostics\.readiness_timeout_seconds must be greater than zero"
    ):
        load_runtime_config(
            _write(tmp_path, "[diagnostics]\nreadiness_timeout_seconds = 0.0\n"),
            env={},
        )
    with pytest.raises(
        ConfigError, match=r"diagnostics\.warmup_timeout_seconds must be greater than zero"
    ):
        load_runtime_config(
            _write(tmp_path, "[diagnostics]\nwarmup_timeout_seconds = 0.0\n"),
            env={},
        )


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "runtime.toml"
    path.write_text(content, encoding="utf-8")
    return path
