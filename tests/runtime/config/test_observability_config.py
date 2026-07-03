"""Runtime observability latency budget configuration tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from iris.runtime.config import (
    ConfigError,
    RuntimeObservabilityConfig,
    default_runtime_config,
    load_runtime_config,
)
from tests.helpers.approx import approx

if TYPE_CHECKING:
    from pathlib import Path


def test_default_observability_config() -> None:
    """デフォルト observability 設定の値が想定通り。"""
    config = default_runtime_config()

    assert config.observability == RuntimeObservabilityConfig()
    assert config.observability.latency_budget.enabled is True
    assert config.observability.latency_budget.handle_observation_ms == approx(3000.0)
    assert config.observability.latency_budget.llm_generate_ms == approx(2200.0)


def test_latency_budget_toml_is_applied(tmp_path: Path) -> None:
    """Latency budget sectionはTOMLからtyped configへ適用される。"""
    config = load_runtime_config(
        _write(
            tmp_path,
            """
            [observability.latency_budget]
            enabled = false
            slow_warning_enabled = false
            handle_observation_ms = 123.0
            runtime_learning_hook_ms = 45.0
            transcript_append_ms = 67.0
            background_enqueue_ms = 89.0
            """,
        ),
        env={},
    )

    budget = config.observability.latency_budget
    assert budget.enabled is False
    assert budget.slow_warning_enabled is False
    assert budget.handle_observation_ms == approx(123.0)
    assert budget.runtime_learning_hook_ms == approx(45.0)
    assert budget.transcript_append_ms == approx(67.0)
    assert budget.background_enqueue_ms == approx(89.0)
    assert budget.llm_generate_ms == approx(2200.0)


def test_latency_budget_unknown_key_is_rejected(tmp_path: Path) -> None:
    """Latency budget sectionの未知keyはConfigError。"""
    with pytest.raises(ConfigError, match=r"observability\.latency_budget\.unexpected"):
        load_runtime_config(
            _write(tmp_path, "[observability.latency_budget]\nunexpected = 1\n"),
            env={},
        )


def test_latency_budget_numeric_values_must_be_positive(tmp_path: Path) -> None:
    """Latency budget の数値は正の値でなければならない。"""
    with pytest.raises(
        ConfigError,
        match=r"observability\.latency_budget\.transcript_append_ms must be greater than zero",
    ):
        load_runtime_config(
            _write(tmp_path, "[observability.latency_budget]\ntranscript_append_ms = 0.0\n"),
            env={},
        )


def test_latency_budget_bool_values_must_be_bool(tmp_path: Path) -> None:
    """Latency budget の真偽値はTOML booleanでなければならない。"""
    with pytest.raises(ConfigError, match=r"observability\.latency_budget\.enabled.*boolean"):
        load_runtime_config(
            _write(tmp_path, '[observability.latency_budget]\nenabled = "yes"\n'),
            env={},
        )


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "runtime.toml"
    path.write_text(content, encoding="utf-8")
    return path
