"""Iris runtime configuration package.

Public re-exports for ``iris.runtime.config``. Internal submodules
(``errors``, ``llm``, ``parsing``, ``root``, ``sources``) are private
implementation details and should not be imported directly by consumers.
"""

from __future__ import annotations

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.llm import (
    LLMProvider,
    ModelSlotName,
    RuntimeModelConfig,
    RuntimeModelsConfig,
    RuntimeOllamaConfig,
    RuntimeOpenAIConfig,
)
from iris.runtime.config.root import (
    CliConfigOverrides,
    IrisRuntimeConfig,
    apply_cli_overrides,
    default_runtime_config,
    load_runtime_config,
    parse_llm_provider,
)

__all__ = [
    "CliConfigOverrides",
    "ConfigError",
    "IrisRuntimeConfig",
    "LLMProvider",
    "ModelSlotName",
    "RuntimeModelConfig",
    "RuntimeModelsConfig",
    "RuntimeOllamaConfig",
    "RuntimeOpenAIConfig",
    "apply_cli_overrides",
    "default_runtime_config",
    "load_runtime_config",
    "parse_llm_provider",
]
