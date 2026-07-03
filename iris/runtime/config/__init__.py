"""Iris runtime configuration package.

Public re-exports for ``iris.runtime.config``. Internal submodules
(``errors``, ``llm``, ``parsing``, ``root``, ``server``, ``sources``, ``state``) are private
implementation details and should not be imported directly by consumers.
"""

from __future__ import annotations

from iris.runtime.config.auth import RuntimeAuthConfig, RuntimeAuthMode
from iris.runtime.config.conversation import RuntimeConversationConfig, RuntimeTranscriptConfig
from iris.runtime.config.delivery import RuntimeDeliveryConfig, RuntimeQuietHoursConfig
from iris.runtime.config.diagnostics import (
    DiagnosticsMode,
    RuntimeDiagnosticsConfig,
    apply_diagnostics_env,
    apply_diagnostics_toml,
)
from iris.runtime.config.errors import ConfigError
from iris.runtime.config.learning import RuntimeLearningConfig
from iris.runtime.config.llm import (
    LLMProvider,
    ModelSlotName,
    RuntimeModelConfig,
    RuntimeModelsConfig,
    RuntimeOllamaConfig,
    RuntimeOpenAIConfig,
)
from iris.runtime.config.logging import RuntimeLoggingConfig
from iris.runtime.config.memory import (
    MemoryEmbeddingProvider,
    MemoryVectorBackend,
    RuntimeMemoryConfig,
    RuntimeMemoryEmbeddingConfig,
    RuntimeMemoryVectorConfig,
    RuntimeMemoryVectorQdrantConfig,
)
from iris.runtime.config.observability import RuntimeObservabilityConfig
from iris.runtime.config.root import (
    IrisRuntimeConfig,
    RuntimeConfigMetadata,
    RuntimeConfigOverrides,
    all_model_slots_are_fake,
    apply_runtime_overrides,
    default_runtime_config,
    discover_default_config_path,
    load_runtime_config,
    normalize_config_path,
    parse_llm_provider,
    resolve_runtime_config_path,
)
from iris.runtime.config.safety import RuntimeSafetyConfig
from iris.runtime.config.scheduler import RuntimeSchedulerConfig
from iris.runtime.config.server import RuntimeServerConfig
from iris.runtime.config.spec import (
    ConfigFieldSpec,
    runtime_config_specs,
    runtime_config_specs_for_version,
)
from iris.runtime.config.state import RuntimeStateConfig

__all__ = [
    "ConfigError",
    "ConfigFieldSpec",
    "DiagnosticsMode",
    "IrisRuntimeConfig",
    "LLMProvider",
    "MemoryEmbeddingProvider",
    "MemoryVectorBackend",
    "ModelSlotName",
    "RuntimeAuthConfig",
    "RuntimeAuthMode",
    "RuntimeConfigMetadata",
    "RuntimeConfigOverrides",
    "RuntimeConversationConfig",
    "RuntimeDeliveryConfig",
    "RuntimeDiagnosticsConfig",
    "RuntimeLearningConfig",
    "RuntimeLoggingConfig",
    "RuntimeMemoryConfig",
    "RuntimeMemoryEmbeddingConfig",
    "RuntimeMemoryVectorConfig",
    "RuntimeMemoryVectorQdrantConfig",
    "RuntimeModelConfig",
    "RuntimeModelsConfig",
    "RuntimeObservabilityConfig",
    "RuntimeOllamaConfig",
    "RuntimeOpenAIConfig",
    "RuntimeQuietHoursConfig",
    "RuntimeSafetyConfig",
    "RuntimeSchedulerConfig",
    "RuntimeServerConfig",
    "RuntimeStateConfig",
    "RuntimeTranscriptConfig",
    "all_model_slots_are_fake",
    "apply_diagnostics_env",
    "apply_diagnostics_toml",
    "apply_runtime_overrides",
    "default_runtime_config",
    "discover_default_config_path",
    "load_runtime_config",
    "normalize_config_path",
    "parse_llm_provider",
    "resolve_runtime_config_path",
    "runtime_config_specs",
    "runtime_config_specs_for_version",
]
