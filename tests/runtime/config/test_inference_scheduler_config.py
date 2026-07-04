"""Runtime inference scheduler config のテスト。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from iris.runtime.config import ConfigError, default_runtime_config, load_runtime_config
from iris.runtime.config.inference_scheduler import RuntimeInferenceSchedulerBusyBehavior

if TYPE_CHECKING:
    from pathlib import Path


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "runtime.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_inference_scheduler_is_disabled_by_default() -> None:
    """Issue #93 scheduler は config-gated で既定無効。"""
    config = default_runtime_config().inference_scheduler

    assert not config.enabled
    assert config.large_llm_concurrency_limit == 1


def test_inference_scheduler_v2_advanced_values_parse(tmp_path: Path) -> None:
    """v2 user config は enabled を表に置き、policy knob は advanced に置く。"""
    path = _write(
        tmp_path,
        """
[config]
version = 2

[inference_scheduler]
enabled = true

[advanced.inference_scheduler]
background_when_busy = "cancel"
small_classifier_concurrency_limit = 3
""".strip(),
    )

    config = load_runtime_config(path, env={}).inference_scheduler

    assert config.enabled
    assert config.background_when_busy is RuntimeInferenceSchedulerBusyBehavior.CANCEL
    assert config.small_classifier_concurrency_limit == 3


def test_inference_scheduler_rejects_large_llm_concurrency_above_one(tmp_path: Path) -> None:
    """Large LLM の同時生成数は policy として1に固定する。"""
    path = _write(
        tmp_path,
        """
[advanced.inference_scheduler]
large_llm_concurrency_limit = 2
""".strip(),
    )

    with pytest.raises(ConfigError, match=r"large_llm_concurrency_limit must be 1"):
        load_runtime_config(path, env={})


def test_inference_scheduler_detail_fields_are_not_v2_top_level(tmp_path: Path) -> None:
    """v2 では scheduler policy knobs を top-level flat schema に追加しない。"""
    path = _write(
        tmp_path,
        """
[inference_scheduler]
background_when_busy = "cancel"
""".strip(),
    )

    with pytest.raises(ConfigError, match=r"Unknown runtime config key"):
        load_runtime_config(path, env={})
