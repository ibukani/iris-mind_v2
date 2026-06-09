"""Iris runtime configuration package.

Public re-exports for ``iris.runtime.config``. Internal submodules
(``errors``, ``llm``, ``parsing``, ``root``, ``server``, ``sources``, ``state``) are private
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
from iris.runtime.config.logging import RuntimeLoggingConfig
from iris.runtime.config.root import (
    IrisRuntimeConfig,
    RuntimeConfigOverrides,
    apply_runtime_overrides,
    default_runtime_config,
    discover_default_config_path,
    load_runtime_config,
    normalize_config_path,
    parse_llm_provider,
)
from iris.runtime.config.server import RuntimeServerConfig
from iris.runtime.config.state import RuntimeStateConfig

__all__ = [
    "ConfigError",
    "IrisRuntimeConfig",
    "LLMProvider",
    "ModelSlotName",
    "RuntimeConfigOverrides",
    "RuntimeLoggingConfig",
    "RuntimeModelConfig",
    "RuntimeModelsConfig",
    "RuntimeOllamaConfig",
    "RuntimeOpenAIConfig",
    "RuntimeServerConfig",
    "RuntimeStateConfig",
    "apply_runtime_overrides",
    "default_runtime_config",
    "discover_default_config_path",
    "load_runtime_config",
    "normalize_config_path",
    "parse_llm_provider",
]
