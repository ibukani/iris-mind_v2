"""LLM config tests."""

from __future__ import annotations

import pytest

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.llm import (
    LLMProvider,
    ModelSlotName,
    RuntimeModelConfig,
    RuntimeModelsConfig,
    RuntimeOllamaConfig,
    RuntimeOpenAIConfig,
    apply_ollama_toml,
    apply_openai_toml,
    apply_toml,
    default_runtime_models_config,
    env_ollama_think,
    model_slot_names,
    replace_runtime_model_config_for_slot,
    runtime_model_config_for_slot,
)


def test_apply_ollama_toml_think_bool() -> None:
    """apply_ollama_toml parses boolean think setting."""
    config = RuntimeOllamaConfig()
    result = apply_ollama_toml(config, {"think": True})
    assert result.think is True

    result = apply_ollama_toml(config, {"think": False})
    assert result.think is False


def test_apply_ollama_toml_think_string() -> None:
    """apply_ollama_toml parses string think setting."""
    config = RuntimeOllamaConfig()
    result = apply_ollama_toml(config, {"think": "low"})
    assert result.think == "low"

    result = apply_ollama_toml(config, {"think": "True"})
    assert result.think is True

    result = apply_ollama_toml(config, {"think": "null"})
    assert result.think is None


def test_apply_ollama_toml_think_invalid() -> None:
    """apply_ollama_toml raises ConfigError for invalid think setting."""
    config = RuntimeOllamaConfig()
    with pytest.raises(ConfigError):
        apply_ollama_toml(config, {"think": "invalid"})


def test_nullable_llm_toml_values_clear_existing_values() -> None:
    """明示的な null は既存の optional 値を解除する。"""
    models = default_runtime_models_config()

    updated_models = apply_toml(
        models,
        {"default_chat": {"max_output_tokens": None}},
    )
    updated_ollama = apply_ollama_toml(
        RuntimeOllamaConfig(keep_alive="5m"),
        {"keep_alive": None},
    )
    updated_openai = apply_openai_toml(
        RuntimeOpenAIConfig(timeout_seconds=10.0, max_output_tokens=42),
        {"timeout_seconds": None, "max_output_tokens": None},
    )

    assert updated_models.default_chat.max_output_tokens is None
    assert updated_ollama.keep_alive is None
    assert updated_openai.timeout_seconds is None
    assert updated_openai.max_output_tokens is None


def test_env_ollama_think_value() -> None:
    """env_ollama_think reads override from environment."""
    assert (
        env_ollama_think({"IRIS_OLLAMA_THINK": "high"}, "IRIS_OLLAMA_THINK", default=False)
        == "high"
    )
    assert (
        env_ollama_think({"IRIS_OLLAMA_THINK": "true"}, "IRIS_OLLAMA_THINK", default=False) is True
    )
    assert env_ollama_think({}, "IRIS_OLLAMA_THINK", default=False) is False


def test_runtime_model_config_for_slot_returns_expected_slot() -> None:
    """runtime_model_config_for_slot returns the matching model slot."""
    models = RuntimeModelsConfig(
        default_chat=RuntimeModelConfig(provider=LLMProvider.FAKE, model="default"),
        fast_judge=RuntimeModelConfig(provider=LLMProvider.OLLAMA, model="fast"),
        reasoning=RuntimeModelConfig(provider=LLMProvider.OPENAI, model="reasoning"),
    )

    assert runtime_model_config_for_slot(models, ModelSlotName.DEFAULT_CHAT).model == "default"
    assert runtime_model_config_for_slot(models, ModelSlotName.FAST_JUDGE).model == "fast"
    assert runtime_model_config_for_slot(models, ModelSlotName.REASONING).model == "reasoning"


def test_model_slot_names_returns_canonical_order() -> None:
    """model_slot_names returns the canonical runtime slot order."""
    assert model_slot_names() == (
        ModelSlotName.DEFAULT_CHAT,
        ModelSlotName.FAST_JUDGE,
        ModelSlotName.REASONING,
    )


def test_replace_runtime_model_config_for_slot_replaces_only_one_slot() -> None:
    """replace_runtime_model_config_for_slot swaps one slot without mutating others."""
    models = RuntimeModelsConfig(
        default_chat=RuntimeModelConfig(provider=LLMProvider.FAKE, model="default"),
        fast_judge=RuntimeModelConfig(provider=LLMProvider.OLLAMA, model="fast"),
        reasoning=RuntimeModelConfig(provider=LLMProvider.OPENAI, model="reasoning"),
    )
    updated = replace_runtime_model_config_for_slot(
        models,
        ModelSlotName.FAST_JUDGE,
        RuntimeModelConfig(provider=LLMProvider.FAKE, model="fast-updated"),
    )

    assert updated.fast_judge.model == "fast-updated"
    assert updated.default_chat == models.default_chat
    assert updated.reasoning == models.reasoning
