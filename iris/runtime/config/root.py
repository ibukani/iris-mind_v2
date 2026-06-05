"""Top-level runtime configuration types, defaults, and load entrypoint.

The precedence order is:

1. CLI overrides
2. Environment variables
3. TOML config file
4. Built-in defaults

TOML is the structured developer configuration. Environment variables are
intended for secrets, deployment overrides, and CI/container overrides. CLI
flags are temporary experiment overrides. The defaults below are the safe
fallback when nothing else is configured.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import os
from pathlib import Path
from typing import TYPE_CHECKING

from iris.runtime.config.llm import (
    LLMProvider,
    RuntimeModelConfig,
    RuntimeModelsConfig,
    RuntimeOllamaConfig,
    RuntimeOpenAIConfig,
    validate_provider,
)
from iris.runtime.config.sources import apply_env, apply_toml, read_toml_file

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.runtime.config.parsing import TomlTable


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
        config = _apply_toml(config, read_toml_file(Path(config_path)))
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
    return validate_provider(value, "models.default_chat.provider")


def _apply_toml(config: IrisRuntimeConfig, table: TomlTable) -> IrisRuntimeConfig:
    """Apply a top-level TOML table to the full runtime config.

    Args:
        config: Base runtime config.
        table: Parsed top-level TOML table.

    Returns:
        Runtime config with TOML values applied.
    """
    models, ollama, openai = apply_toml(
        config.models,
        config.ollama,
        config.openai,
        table,
    )
    return replace(config, models=models, ollama=ollama, openai=openai)


def _apply_env(
    config: IrisRuntimeConfig,
    env: Mapping[str, str],
) -> IrisRuntimeConfig:
    """Apply environment variable overrides to the full runtime config.

    Args:
        config: Base runtime config.
        env: Environment variable mapping.

    Returns:
        Runtime config with environment values applied.
    """
    models, ollama, openai = apply_env(config.models, config.ollama, config.openai, env)
    return replace(config, models=models, ollama=ollama, openai=openai)
