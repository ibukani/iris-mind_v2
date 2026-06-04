"""Runtime configuration loading for Iris."""

from __future__ import annotations

from dataclasses import dataclass, replace
import os
from pathlib import Path
import tomllib
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from typing import BinaryIO

LLMProvider = Literal["fake", "ollama", "openai"]
ModelSlotName = Literal["default_chat", "fast_judge", "reasoning"]

_VALID_PROVIDERS: frozenset[str] = frozenset(("fake", "ollama", "openai"))
_MODEL_SLOTS: tuple[ModelSlotName, ...] = ("default_chat", "fast_judge", "reasoning")

type _TomlScalar = str | int | float | bool | None
type _TomlValue = _TomlScalar | _TomlArray | _TomlTable
type _TomlArray = list[_TomlValue]
type _TomlTable = dict[str, _TomlValue]

_load_toml: Callable[[BinaryIO], _TomlTable] = tomllib.load


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


@dataclass(frozen=True)
class IrisRuntimeConfig:
    """Runtime configuration used by application wiring."""

    models: RuntimeModelsConfig
    ollama: RuntimeOllamaConfig
    openai: RuntimeOpenAIConfig


@dataclass(frozen=True)
class CliConfigOverrides:
    """Configuration overrides supplied by CLI flags."""

    llm: LLMProvider | None = None
    model: str | None = None
    ollama_host: str | None = None


class ConfigError(RuntimeError):
    """Raised when runtime configuration is invalid."""


def default_runtime_config() -> IrisRuntimeConfig:
    """Create the default runtime configuration.

    Returns:
        Default runtime configuration.
    """
    return IrisRuntimeConfig(
        models=RuntimeModelsConfig(
            default_chat=RuntimeModelConfig(provider="fake", model="fake-llm"),
            fast_judge=RuntimeModelConfig(
                provider="fake",
                model="fake-llm",
                max_output_tokens=128,
            ),
            reasoning=RuntimeModelConfig(
                provider="fake",
                model="fake-llm",
                max_output_tokens=1024,
            ),
        ),
        ollama=RuntimeOllamaConfig(),
        openai=RuntimeOpenAIConfig(),
    )


def load_runtime_config(
    config_path: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    cli_overrides: CliConfigOverrides | None = None,
) -> IrisRuntimeConfig:
    """Load runtime config from defaults, TOML, environment, and CLI overrides.

    Args:
        config_path: Optional explicit TOML file path.
        env: Environment mapping. Defaults to ``os.environ``.
        cli_overrides: Optional CLI override values.

    Returns:
        Validated runtime configuration.

    """
    config = default_runtime_config()
    if config_path is not None:
        config = _apply_toml(config, _read_toml(Path(config_path)))
    config = _apply_env(config, os.environ if env is None else env)
    if cli_overrides is not None:
        config = apply_cli_overrides(config, cli_overrides)
    return config


def apply_cli_overrides(
    config: IrisRuntimeConfig,
    overrides: CliConfigOverrides,
) -> IrisRuntimeConfig:
    """Apply CLI overrides to an existing runtime config.

    Args:
        config: Base runtime config.
        overrides: CLI override values.

    Returns:
        Runtime config with CLI values applied.
    """
    default_chat = config.models.default_chat
    if overrides.llm is not None:
        default_chat = replace(default_chat, provider=overrides.llm)
    if overrides.model is not None:
        default_chat = replace(default_chat, model=overrides.model)

    ollama = config.ollama
    if overrides.ollama_host is not None:
        ollama = replace(ollama, base_url=overrides.ollama_host)

    return replace(
        config,
        models=replace(config.models, default_chat=default_chat),
        ollama=ollama,
    )


def parse_llm_provider(value: str) -> LLMProvider:
    """Parse and validate an LLM provider name.

    Args:
        value: Provider name from CLI or config.

    Returns:
        Typed provider name.

    """
    return _provider(value, "models.default_chat.provider")


def _read_toml(path: Path) -> _TomlTable:
    if not path.exists():
        message = f"Runtime config file does not exist: {path}"
        raise ConfigError(message)
    with path.open("rb") as file:
        return _load_toml(file)


def _apply_toml(config: IrisRuntimeConfig, table: _TomlTable) -> IrisRuntimeConfig:
    models = _table_or_empty(table, "models")
    return replace(
        config,
        models=RuntimeModelsConfig(
            default_chat=_apply_model_table(
                config.models.default_chat,
                _table_or_empty(models, "default_chat"),
                "models.default_chat",
            ),
            fast_judge=_apply_model_table(
                config.models.fast_judge,
                _table_or_empty(models, "fast_judge"),
                "models.fast_judge",
            ),
            reasoning=_apply_model_table(
                config.models.reasoning,
                _table_or_empty(models, "reasoning"),
                "models.reasoning",
            ),
        ),
        ollama=_apply_ollama_table(config.ollama, _table_or_empty(table, "ollama")),
        openai=_apply_openai_table(config.openai, _table_or_empty(table, "openai")),
    )


def _apply_model_table(
    config: RuntimeModelConfig,
    table: _TomlTable,
    path: str,
) -> RuntimeModelConfig:
    provider = config.provider
    model = config.model
    temperature = config.temperature
    max_output_tokens = config.max_output_tokens

    if "provider" in table:
        provider = _provider(_string_value(table["provider"], f"{path}.provider"), path)
    if "model" in table:
        model = _string_value(table["model"], f"{path}.model")
    if "temperature" in table:
        temperature = _float_value(table["temperature"], f"{path}.temperature")
    if "max_output_tokens" in table:
        max_output_tokens = _optional_int_value(
            table["max_output_tokens"],
            f"{path}.max_output_tokens",
        )
    return RuntimeModelConfig(
        provider=provider,
        model=model,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )


def _apply_ollama_table(config: RuntimeOllamaConfig, table: _TomlTable) -> RuntimeOllamaConfig:
    base_url = config.base_url
    timeout_seconds = config.timeout_seconds
    keep_alive = config.keep_alive

    if "base_url" in table:
        base_url = _string_value(table["base_url"], "ollama.base_url")
    if "timeout_seconds" in table:
        timeout_seconds = _float_value(table["timeout_seconds"], "ollama.timeout_seconds")
    if "keep_alive" in table:
        keep_alive = _optional_string_value(table["keep_alive"], "ollama.keep_alive")
    return RuntimeOllamaConfig(
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        keep_alive=keep_alive,
    )


def _apply_openai_table(config: RuntimeOpenAIConfig, table: _TomlTable) -> RuntimeOpenAIConfig:
    model = config.model
    timeout_seconds = config.timeout_seconds
    max_output_tokens = config.max_output_tokens

    if "model" in table:
        model = _string_value(table["model"], "openai.model")
    if "timeout_seconds" in table:
        timeout_seconds = _optional_float_value(table["timeout_seconds"], "openai.timeout_seconds")
    if "max_output_tokens" in table:
        max_output_tokens = _optional_int_value(
            table["max_output_tokens"],
            "openai.max_output_tokens",
        )
    return RuntimeOpenAIConfig(
        model=model,
        timeout_seconds=timeout_seconds,
        max_output_tokens=max_output_tokens,
    )


def _apply_env(config: IrisRuntimeConfig, env: Mapping[str, str]) -> IrisRuntimeConfig:
    models = config.models
    for slot in _MODEL_SLOTS:
        model_config = _apply_model_env(_slot_config(models, slot), slot, env)
        models = _replace_slot(models, slot, model_config)
    return replace(
        config,
        models=models,
        ollama=_apply_ollama_env(config.ollama, env),
        openai=_apply_openai_env(config.openai, env),
    )


def _apply_model_env(
    config: RuntimeModelConfig,
    slot: ModelSlotName,
    env: Mapping[str, str],
) -> RuntimeModelConfig:
    prefix = f"IRIS_{slot.upper()}_"
    provider = _env_provider(env, f"{prefix}PROVIDER", config.provider, slot)
    model = env.get(f"{prefix}MODEL", config.model)
    temperature = _env_float(env, f"{prefix}TEMPERATURE", config.temperature)
    max_output_tokens = _env_optional_int(
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


def _apply_ollama_env(config: RuntimeOllamaConfig, env: Mapping[str, str]) -> RuntimeOllamaConfig:
    return RuntimeOllamaConfig(
        base_url=env.get("IRIS_OLLAMA_HOST", config.base_url),
        timeout_seconds=_env_float(
            env,
            "IRIS_OLLAMA_TIMEOUT_SECONDS",
            config.timeout_seconds,
        ),
        keep_alive=env.get("IRIS_OLLAMA_KEEP_ALIVE", config.keep_alive),
    )


def _apply_openai_env(config: RuntimeOpenAIConfig, env: Mapping[str, str]) -> RuntimeOpenAIConfig:
    return RuntimeOpenAIConfig(
        model=env.get("IRIS_OPENAI_MODEL", config.model),
        timeout_seconds=_env_optional_float(
            env,
            "IRIS_OPENAI_TIMEOUT_SECONDS",
            config.timeout_seconds,
        ),
        max_output_tokens=_env_optional_int(
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
    if slot == "default_chat":
        return replace(models, default_chat=config)
    if slot == "fast_judge":
        return replace(models, fast_judge=config)
    return replace(models, reasoning=config)


def _slot_config(models: RuntimeModelsConfig, slot: ModelSlotName) -> RuntimeModelConfig:
    if slot == "default_chat":
        return models.default_chat
    if slot == "fast_judge":
        return models.fast_judge
    return models.reasoning


def _table_or_empty(table: _TomlTable, key: str) -> _TomlTable:
    value = table.get(key)
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    message = f"Runtime config section '{key}' must be a table"
    raise ConfigError(message)


def _provider(value: str, path: str) -> LLMProvider:
    if value == "fake":
        return "fake"
    if value == "ollama":
        return "ollama"
    if value == "openai":
        return "openai"
    message = f"Invalid LLM provider for {path}: {value}"
    raise ConfigError(message)


def _env_provider(
    env: Mapping[str, str],
    key: str,
    default: LLMProvider,
    slot: ModelSlotName,
) -> LLMProvider:
    value = env.get(key)
    if value is None:
        return default
    return _provider(value, f"models.{slot}.provider")


def _string_value(value: _TomlValue, path: str) -> str:
    if isinstance(value, str):
        return value
    message = f"Runtime config value '{path}' must be a string"
    raise ConfigError(message)


def _optional_string_value(value: _TomlValue, path: str) -> str | None:
    if value is None or isinstance(value, str):
        return value
    message = f"Runtime config value '{path}' must be a string or null"
    raise ConfigError(message)


def _float_value(value: _TomlValue, path: str) -> float:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    message = f"Runtime config value '{path}' must be a float"
    raise ConfigError(message)


def _optional_float_value(value: _TomlValue, path: str) -> float | None:
    if value is None:
        return None
    return _float_value(value, path)


def _optional_int_value(value: _TomlValue, path: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    message = f"Runtime config value '{path}' must be an integer or null"
    raise ConfigError(message)


def _env_float(env: Mapping[str, str], key: str, default: float) -> float:
    value = env.get(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        message = f"Environment variable {key} must be a float"
        raise ConfigError(message) from exc


def _env_optional_float(env: Mapping[str, str], key: str, default: float | None) -> float | None:
    value = env.get(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        message = f"Environment variable {key} must be a float"
        raise ConfigError(message) from exc


def _env_optional_int(env: Mapping[str, str], key: str, default: int | None) -> int | None:
    value = env.get(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        message = f"Environment variable {key} must be an integer"
        raise ConfigError(message) from exc
