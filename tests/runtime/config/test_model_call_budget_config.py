"""Runtime model call budget config tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from iris.contracts.model_policy import CascadeFallbackBehavior
from iris.runtime.config import ConfigError, default_runtime_config, load_runtime_config
from iris.runtime.config.model_call_budget import (
    RuntimeFeatureModelCallBudget,
    RuntimeModelCallBudgetConfig,
    validate_model_call_budget_config,
)


def test_default_model_call_budget_config_matches_issue_88_hot_path_policy() -> None:
    """既定設定は user-facing large LLM を 1 回、hook direct large LLM を 0 回にする。"""
    config = default_runtime_config().model_call_budget

    assert config.enabled
    assert config.user_response_hot_path.large_llm_max_calls == 1
    assert config.event_reaction.large_llm_max_calls == 1
    assert config.runtime_learning_hook.large_llm_max_calls == 0
    assert config.runtime_learning_hook.enqueue_only
    assert (
        config.user_response_hot_path.low_confidence_fallback
        is CascadeFallbackBehavior.DETERMINISTIC_BASELINE
    )


def test_model_call_budget_toml_override_is_loaded(tmp_path: Path) -> None:
    """TOML で feature 別 budget と fallback を上書きできる。"""
    config_path = tmp_path / "runtime.toml"
    config_path.write_text(
        """
[config]
version = 2

[advanced.model_call_budget.user_response_hot_path]
confidence_threshold = 0.5
low_confidence_fallback = "no_op"

[advanced.model_call_budget.memory_extraction]
small_classifier_max_calls = 2
""".strip(),
        encoding="utf-8",
    )

    config = load_runtime_config(config_path, env={})

    confidence_threshold = config.model_call_budget.user_response_hot_path.confidence_threshold
    assert abs(confidence_threshold - 0.5) < 1e-9
    assert (
        config.model_call_budget.user_response_hot_path.low_confidence_fallback
        is CascadeFallbackBehavior.NO_OP
    )
    assert config.model_call_budget.memory_extraction.small_classifier_max_calls == 2


def test_user_response_hot_path_rejects_more_than_one_large_llm_call() -> None:
    """user-facing hot path は large LLM 2 回以上を設定できない。"""
    config = RuntimeModelCallBudgetConfig(
        user_response_hot_path=RuntimeFeatureModelCallBudget(large_llm_max_calls=2)
    )

    with pytest.raises(ConfigError, match="large_llm_max_calls"):
        validate_model_call_budget_config(config)


def test_runtime_learning_hook_must_remain_enqueue_only() -> None:
    """Runtime learning hook は direct large LLM を許可しない enqueue-only 契約に固定する。"""
    config = RuntimeModelCallBudgetConfig(
        runtime_learning_hook=RuntimeFeatureModelCallBudget(enqueue_only=False)
    )

    with pytest.raises(ConfigError, match="enqueue_only"):
        validate_model_call_budget_config(config)


def test_model_call_budget_rejects_negative_and_invalid_fallback(tmp_path: Path) -> None:
    """不正な call budget 値と fallback 値は config load 時に拒否される。"""
    negative_path = tmp_path / "negative.toml"
    negative_path.write_text(
        """
[config]
version = 2

[advanced.model_call_budget.user_response_hot_path]
large_llm_max_calls = -1
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="greater than or equal"):
        load_runtime_config(negative_path, env={})

    fallback_path = tmp_path / "fallback.toml"
    fallback_path.write_text(
        """
[config]
version = 2

[advanced.model_call_budget.user_response_hot_path]
low_confidence_fallback = "unknown"
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Invalid"):
        load_runtime_config(fallback_path, env={})
