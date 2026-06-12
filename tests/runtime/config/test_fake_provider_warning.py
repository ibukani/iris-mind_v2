"""fake プロバイダ検出とランタイム起動警告のテスト。"""

from __future__ import annotations

from dataclasses import replace

from iris.runtime.config import (
    all_model_slots_are_fake,
    default_runtime_config,
)
from iris.runtime.config.llm import RuntimeModelConfig


def test_default_config_is_all_fake() -> None:
    """デフォルト設定は全モデルスロットが fake と判定される。"""
    config = default_runtime_config()
    assert all_model_slots_are_fake(config) is True


def test_mixed_provider_config_is_not_all_fake() -> None:
    """一部のスロットだけ実プロバイダの場合、all_fake は False。"""
    config = default_runtime_config()
    config = replace(
        config,
        models=replace(
            config.models,
            default_chat=RuntimeModelConfig(provider="openai", model="gpt-5-mini"),
        ),
    )
    assert all_model_slots_are_fake(config) is False


def test_all_real_provider_config_is_not_all_fake() -> None:
    """全スロットが実プロバイダの場合、all_fake は False。"""
    config = default_runtime_config()
    config = replace(
        config,
        models=replace(
            config.models,
            default_chat=RuntimeModelConfig(provider="openai", model="gpt-5-mini"),
            fast_judge=RuntimeModelConfig(
                provider="ollama", model="qwen3:8b", max_output_tokens=128
            ),
            reasoning=RuntimeModelConfig(
                provider="ollama", model="qwen3:8b", max_output_tokens=1024
            ),
        ),
    )
    assert all_model_slots_are_fake(config) is False


def test_partial_fake_config_is_not_all_fake() -> None:
    """fast_judge だけ fake の場合は all_fake ではない。"""
    config = default_runtime_config()
    config = replace(
        config,
        models=replace(
            config.models,
            default_chat=RuntimeModelConfig(provider="ollama", model="qwen3:8b"),
        ),
    )
    assert all_model_slots_are_fake(config) is False
