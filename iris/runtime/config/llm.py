"""LLM-related runtime configuration types and source application logic."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.parsing import (
    TomlTable,
    env_float,
    env_optional_float,
    env_optional_int,
    parse_float,
    parse_optional_float,
    parse_optional_int,
    parse_optional_string,
    parse_string,
    table_or_empty,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

LLMProvider = Literal["fake", "ollama", "openai"]
ModelSlotName = Literal["default_chat", "fast_judge", "reasoning"]

_VALID_PROVIDERS: frozenset[str] = frozenset(("fake", "ollama", "openai"))
_MODEL_SLOTS: tuple[ModelSlotName, ...] = ("default_chat", "fast_judge", "reasoning")


def is_valid_provider(value: str) -> bool:
    """Return whether a string is a recognised LLM provider.

    Args:
        value: Provider name to check.

    Returns:
        True if the value is a supported LLM provider.
    """
    return value in _VALID_PROVIDERS


def validate_provider(value: str, path: str) -> LLMProvider:
    """Validate a provider name and return the typed literal.

    Args:
        value: Provider name to validate.
        path: Config path used in error messages.

    Returns:
        The validated provider literal.

    Raises:
        ConfigError: If the provider name is not recognised.
    """
    if value == "fake":
        return "fake"
    if value == "ollama":
        return "ollama"
    if value == "openai":
        return "openai"
    message = f"Invalid LLM provider for {path}: {value}"
    raise ConfigError(message)


def env_provider(
    env: Mapping[str, str],
    key: str,
    default: LLMProvider,
    slot: ModelSlotName,
) -> LLMProvider:
    """Read a provider override from the environment.

    Args:
        env: Environment variable mapping.
        key: Variable name to look up.
        default: Default provider to return when the variable is absent.
        slot: Model slot used in error messages.

    Returns:
        Validated provider literal or the default.
    """
    value = env.get(key)
    if value is None:
        return default
    return validate_provider(value, f"models.{slot}.provider")


@dataclass(frozen=True)
class RuntimeModelConfig:
    """Runtime configuration for one named model slot."""

    provider: LLMProvider
    model: str
    temperature: float = 0.0
    max_output_tokens: int | None = None


@dataclass(frozen=True)
class RuntimeModelsConfig:
    """Runtime configuration for all named model slots."""

    default_chat: RuntimeModelConfig
    fast_judge: RuntimeModelConfig
    reasoning: RuntimeModelConfig


@dataclass(frozen=True)
class RuntimeOllamaConfig:
    """Runtime configuration shared by Ollama model slots."""

    base_url: str = "http://localhost:11434"
    timeout_seconds: float = 120.0
    keep_alive: str | None = None


@dataclass(frozen=True)
class RuntimeOpenAIConfig:
    """Runtime configuration shared by OpenAI model slots."""

    model: str = "gpt-5-mini"
    timeout_seconds: float | None = None
    max_output_tokens: int | None = None


def apply_toml(config: RuntimeModelsConfig, models_table: TomlTable) -> RuntimeModelsConfig:
    """Apply the TOML ``[models.*]`` section to a models config.

    Args:
        config: Base models config.
        models_table: Parsed TOML ``[models]`` table.

    Returns:
        Models config with TOML values applied.
    """
    return RuntimeModelsConfig(
        default_chat=_apply_model_table(
            config.default_chat,
            table_or_empty(models_table, "default_chat"),
            "models.default_chat",
        ),
        fast_judge=_apply_model_table(
            config.fast_judge,
            table_or_empty(models_table, "fast_judge"),
            "models.fast_judge",
        ),
        reasoning=_apply_model_table(
            config.reasoning,
            table_or_empty(models_table, "reasoning"),
            "models.reasoning",
        ),
    )


def apply_ollama_toml(
    config: RuntimeOllamaConfig,
    ollama_table: TomlTable,
) -> RuntimeOllamaConfig:
    """Apply the TOML ``[ollama]`` section to an Ollama config.

    Args:
        config: Base Ollama config.
        ollama_table: Parsed TOML ``[ollama]`` table.

    Returns:
        Ollama config with TOML values applied.
    """
    base_url = config.base_url
    timeout_seconds = config.timeout_seconds
    keep_alive = config.keep_alive

    if "base_url" in ollama_table:
        base_url = parse_string(ollama_table["base_url"], "ollama.base_url")
    if "timeout_seconds" in ollama_table:
        timeout_seconds = parse_float(ollama_table["timeout_seconds"], "ollama.timeout_seconds")
    if "keep_alive" in ollama_table:
        keep_alive = parse_optional_string(ollama_table["keep_alive"], "ollama.keep_alive")
    return RuntimeOllamaConfig(
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        keep_alive=keep_alive,
    )


def apply_openai_toml(
    config: RuntimeOpenAIConfig,
    openai_table: TomlTable,
) -> RuntimeOpenAIConfig:
    """Apply the TOML ``[openai]`` section to an OpenAI config.

    Args:
        config: Base OpenAI config.
        openai_table: Parsed TOML ``[openai]`` table.

    Returns:
        OpenAI config with TOML values applied.
    """
    model = config.model
    timeout_seconds = config.timeout_seconds
    max_output_tokens = config.max_output_tokens

    if "model" in openai_table:
        model = parse_string(openai_table["model"], "openai.model")
    if "timeout_seconds" in openai_table:
        timeout_seconds = parse_optional_float(
            openai_table["timeout_seconds"],
            "openai.timeout_seconds",
        )
    if "max_output_tokens" in openai_table:
        max_output_tokens = parse_optional_int(
            openai_table["max_output_tokens"],
            "openai.max_output_tokens",
        )
    return RuntimeOpenAIConfig(
        model=model,
        timeout_seconds=timeout_seconds,
        max_output_tokens=max_output_tokens,
    )


def apply_env(
    config: RuntimeModelsConfig,
    ollama: RuntimeOllamaConfig,
    openai: RuntimeOpenAIConfig,
    env: Mapping[str, str],
) -> tuple[RuntimeModelsConfig, RuntimeOllamaConfig, RuntimeOpenAIConfig]:
    """Apply environment variable overrides to LLM config sections.

    Args:
        config: Base models config.
        ollama: Base Ollama config.
        openai: Base OpenAI config.
        env: Environment variable mapping.

    Returns:
        Updated models, Ollama, and OpenAI configs.
    """
    updated_models = config
    for slot in _MODEL_SLOTS:
        slot_config = _slot_config(updated_models, slot)
        updated_models = _replace_slot(
            updated_models,
            slot,
            _apply_model_env(slot_config, slot, env),
        )
    return (
        updated_models,
        _apply_ollama_env(ollama, env),
        _apply_openai_env(openai, env),
    )


def _apply_model_table(
    config: RuntimeModelConfig,
    table: TomlTable,
    path: str,
) -> RuntimeModelConfig:
    """Apply a single model slot TOML table to a model config.

    Args:
        config: Base model config.
        table: Parsed TOML table for the model slot.
        path: Config path used in error messages.

    Returns:
        Model config with TOML values applied.
    """
    provider = config.provider
    model = config.model
    temperature = config.temperature
    max_output_tokens = config.max_output_tokens

    if "provider" in table:
        provider = validate_provider(
            parse_string(table["provider"], f"{path}.provider"),
            path,
        )
    if "model" in table:
        model = parse_string(table["model"], f"{path}.model")
    if "temperature" in table:
        temperature = parse_float(table["temperature"], f"{path}.temperature")
    if "max_output_tokens" in table:
        max_output_tokens = parse_optional_int(
            table["max_output_tokens"],
            f"{path}.max_output_tokens",
        )
    return RuntimeModelConfig(
        provider=provider,
        model=model,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )


def _apply_model_env(
    config: RuntimeModelConfig,
    slot: ModelSlotName,
    env: Mapping[str, str],
) -> RuntimeModelConfig:
    """Apply environment variable overrides to one model slot.

    Args:
        config: Base model config.
        slot: Model slot name used to build the env var prefix.
        env: Environment variable mapping.

    Returns:
        Model config with environment values applied.
    """
    prefix = f"IRIS_{slot.upper()}_"
    provider = env_provider(env, f"{prefix}PROVIDER", config.provider, slot)
    model = env.get(f"{prefix}MODEL", config.model)
    temperature = env_float(env, f"{prefix}TEMPERATURE", config.temperature)
    max_output_tokens = env_optional_int(
        env,
        f"{prefix}MAX_OUTPUT_TOKENS",
        config.max_output_tokens,
    )
    return RuntimeModelConfig(
        provider=provider,
        model=model,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )


def _apply_ollama_env(
    config: RuntimeOllamaConfig,
    env: Mapping[str, str],
) -> RuntimeOllamaConfig:
    """Apply environment variable overrides to the Ollama config.

    Args:
        config: Base Ollama config.
        env: Environment variable mapping.

    Returns:
        Ollama config with environment values applied.
    """
    return RuntimeOllamaConfig(
        base_url=env.get("IRIS_OLLAMA_HOST", config.base_url),
        timeout_seconds=env_float(
            env,
            "IRIS_OLLAMA_TIMEOUT_SECONDS",
            config.timeout_seconds,
        ),
        keep_alive=env.get("IRIS_OLLAMA_KEEP_ALIVE", config.keep_alive),
    )


def _apply_openai_env(
    config: RuntimeOpenAIConfig,
    env: Mapping[str, str],
) -> RuntimeOpenAIConfig:
    """Apply environment variable overrides to the OpenAI config.

    Args:
        config: Base OpenAI config.
        env: Environment variable mapping.

    Returns:
        OpenAI config with environment values applied.
    """
    return RuntimeOpenAIConfig(
        model=env.get("IRIS_OPENAI_MODEL", config.model),
        timeout_seconds=env_optional_float(
            env,
            "IRIS_OPENAI_TIMEOUT_SECONDS",
            config.timeout_seconds,
        ),
        max_output_tokens=env_optional_int(
            env,
            "IRIS_OPENAI_MAX_OUTPUT_TOKENS",
            config.max_output_tokens,
        ),
    )


def _replace_slot(
    models: RuntimeModelsConfig,
    slot: ModelSlotName,
    config: RuntimeModelConfig,
) -> RuntimeModelsConfig:
    """Return a copy of ``models`` with the named slot replaced.

    Args:
        models: Base models config.
        slot: Slot name to replace.
        config: New model config for the slot.

    Returns:
        Models config with the slot replaced.
    """
    if slot == "default_chat":
        return replace(models, default_chat=config)
    if slot == "fast_judge":
        return replace(models, fast_judge=config)
    return replace(models, reasoning=config)


def _slot_config(
    models: RuntimeModelsConfig,
    slot: ModelSlotName,
) -> RuntimeModelConfig:
    """Return the current config for a named model slot.

    Args:
        models: Models config to read from.
        slot: Slot name to read.

    Returns:
        Model config stored at the named slot.
    """
    if slot == "default_chat":
        return models.default_chat
    if slot == "fast_judge":
        return models.fast_judge
    return models.reasoning
