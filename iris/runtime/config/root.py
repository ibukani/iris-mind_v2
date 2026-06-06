"""Top-level runtime configuration types, defaults, and load entrypoint.

The precedence order is:

1. Built-in defaults
2. TOML config file
3. Environment variables
4. CLI overrides

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
from iris.runtime.config.parsing import table_or_empty
from iris.runtime.config.server import (
    RuntimeServerConfig,
    apply_server_env,
    apply_server_toml,
    validate_server_config,
    validate_server_port,
)
from iris.runtime.config.sources import apply_env, apply_toml, read_toml_file
from iris.runtime.config.state import (
    RuntimeStateConfig,
    apply_state_env,
    apply_state_toml,
    validate_state_config,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.runtime.config.parsing import TomlTable


@dataclass(frozen=True)
class IrisRuntimeConfig:
    """Runtime configuration used by application wiring."""

    server: RuntimeServerConfig
    state: RuntimeStateConfig
    models: RuntimeModelsConfig
    ollama: RuntimeOllamaConfig
    openai: RuntimeOpenAIConfig


@dataclass(frozen=True)
class RuntimeConfigOverrides:
    """Configuration overrides supplied at runtime initialization."""

    llm: LLMProvider | None = None
    model: str | None = None
    ollama_host: str | None = None
    server_host: str | None = None
    server_port: int | None = None


def default_runtime_config() -> IrisRuntimeConfig:
    """Create the default runtime configuration.

    Returns:
        Default runtime configuration.
    """
    return IrisRuntimeConfig(
        server=RuntimeServerConfig(),
        state=RuntimeStateConfig(),
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
    overrides: RuntimeConfigOverrides | None = None,
) -> IrisRuntimeConfig:
    """Load runtime config from defaults, TOML, environment, and overrides.

    Args:
        config_path: Optional explicit TOML file path.
        env: Environment mapping. Defaults to ``os.environ``.
        overrides: Optional override values.

    Returns:
        Validated runtime configuration.
    """
    config = default_runtime_config()
    if config_path is not None:
        config = _apply_toml(config, read_toml_file(Path(config_path)))
    config = _apply_env(config, os.environ if env is None else env)
    if overrides is not None:
        config = apply_runtime_overrides(config, overrides)

    config = replace(config, server=validate_server_config(config.server))
    return replace(config, state=validate_state_config(config.state))


def apply_runtime_overrides(
    config: IrisRuntimeConfig,
    overrides: RuntimeConfigOverrides,
) -> IrisRuntimeConfig:
    """Apply overrides to an existing runtime config.

    Args:
        config: Base runtime config.
        overrides: Override values.

    Returns:
        Runtime config with overrides applied.
    """
    default_chat = config.models.default_chat
    if overrides.llm is not None:
        default_chat = replace(default_chat, provider=overrides.llm)
    if overrides.model is not None:
        default_chat = replace(default_chat, model=overrides.model)

    ollama = config.ollama
    if overrides.ollama_host is not None:
        ollama = replace(ollama, base_url=overrides.ollama_host)

    server = config.server
    if overrides.server_host is not None:
        server = replace(server, host=overrides.server_host)
    if overrides.server_port is not None:
        port = validate_server_port(overrides.server_port, source="server_port override")
        server = replace(server, port=port)

    return replace(
        config,
        server=server,
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
    server = apply_server_toml(config.server, table_or_empty(table, "server"))
    state = apply_state_toml(config.state, table_or_empty(table, "state"))

    models, ollama, openai = apply_toml(
        config.models,
        config.ollama,
        config.openai,
        table,
    )
    return replace(config, server=server, state=state, models=models, ollama=ollama, openai=openai)


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
    server = apply_server_env(config.server, env)
    state = apply_state_env(config.state, env)

    models, ollama, openai = apply_env(config.models, config.ollama, config.openai, env)
    return replace(config, server=server, state=state, models=models, ollama=ollama, openai=openai)
