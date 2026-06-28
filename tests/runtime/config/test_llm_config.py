"""LLM config tests."""

from __future__ import annotations

import pytest

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.llm import RuntimeOllamaConfig, apply_ollama_toml, env_ollama_think


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
