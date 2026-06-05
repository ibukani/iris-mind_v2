"""TOML file loading and top-level source application for runtime config."""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.llm import (
    RuntimeModelsConfig,
    RuntimeOllamaConfig,
    RuntimeOpenAIConfig,
    apply_ollama_toml,
    apply_openai_toml,
)
from iris.runtime.config.llm import apply_env as apply_llm_env
from iris.runtime.config.llm import apply_toml as apply_llm_toml
from iris.runtime.config.parsing import TomlTable, load_toml, table_or_empty

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


def read_toml_file(path: Path) -> TomlTable:
    """Read a TOML config file from disk.

    Args:
        path: Path to the TOML file.

    Returns:
        Parsed top-level TOML table.

    Raises:
        ConfigError: If the file does not exist.
    """
    if not path.exists():
        message = f"Runtime config file does not exist: {path}"
        raise ConfigError(message)
    with path.open("rb") as file:
        return load_toml(file)


def apply_toml(
    models: RuntimeModelsConfig,
    ollama: RuntimeOllamaConfig,
    openai: RuntimeOpenAIConfig,
    table: TomlTable,
) -> tuple[RuntimeModelsConfig, RuntimeOllamaConfig, RuntimeOpenAIConfig]:
    """Apply a top-level TOML table to the LLM config sections.

    Args:
        models: Base models config.
        ollama: Base Ollama config.
        openai: Base OpenAI config.
        table: Top-level TOML table.

    Returns:
        Updated models, Ollama, and OpenAI configs.
    """
    updated_models = apply_llm_toml(models, table_or_empty(table, "models"))
    updated_ollama = apply_ollama_toml(ollama, table_or_empty(table, "ollama"))
    updated_openai = apply_openai_toml(openai, table_or_empty(table, "openai"))
    return updated_models, updated_ollama, updated_openai


def apply_env(
    models: RuntimeModelsConfig,
    ollama: RuntimeOllamaConfig,
    openai: RuntimeOpenAIConfig,
    env: Mapping[str, str],
) -> tuple[RuntimeModelsConfig, RuntimeOllamaConfig, RuntimeOpenAIConfig]:
    """Apply environment variable overrides to the LLM config sections.

    Args:
        models: Base models config.
        ollama: Base Ollama config.
        openai: Base OpenAI config.
        env: Environment variable mapping.

    Returns:
        Updated models, Ollama, and OpenAI configs.
    """
    return apply_llm_env(models, ollama, openai, env)
