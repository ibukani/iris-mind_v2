"""Runtime state persistence configuration."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Mapping

from iris.runtime.config.errors import ConfigError

if TYPE_CHECKING:
    from iris.runtime.config.parsing import TomlTable


@dataclass(frozen=True)
class RuntimeStateConfig:
    """Configuration for persistent state and storage."""

    backend: Literal["memory", "sqlite"] = "memory"
    sqlite_path: str = ".iris/runtime/state.sqlite3"


def validate_backend(value: str, path: str) -> Literal["memory", "sqlite"]:
    """Validate a backend name and return the typed literal.

    Args:
        value: Backend name to validate.
        path: Configuration path for error messages.

    Returns:
        Literal["memory", "sqlite"]: Validated backend name.

    Raises:
        ConfigError: If backend name is invalid.
    """
    if value == "memory":
        return "memory"
    if value == "sqlite":
        return "sqlite"
    message = f"Invalid {path}: {value}"
    raise ConfigError(message)


def validate_state_config(config: RuntimeStateConfig) -> RuntimeStateConfig:
    """Validate state configuration constraints.

    Args:
        config: The state config to validate.

    Returns:
        RuntimeStateConfig: The validated config.

    Raises:
        ConfigError: If constraints are violated.
    """
    if config.backend not in {"memory", "sqlite"}:
        message = f"Invalid state.backend: {config.backend}"
        raise ConfigError(message)
    if config.backend == "sqlite" and not config.sqlite_path:
        message = "state.sqlite_path must be non-empty when backend is sqlite"
        raise ConfigError(message)
    return config


def apply_state_toml(config: RuntimeStateConfig, table: TomlTable) -> RuntimeStateConfig:
    """Apply TOML overrides to state config.

    Args:
        config: Base state config.
        table: Parsed TOML table for state.

    Returns:
        State config with TOML values applied.
    """
    backend = config.backend
    sqlite_path = config.sqlite_path

    if "backend" in table:
        value = str(table["backend"])
        backend = validate_backend(value, "state.backend in TOML")

    if "sqlite_path" in table:
        sqlite_path = str(table["sqlite_path"])

    new_config = replace(config, backend=backend, sqlite_path=sqlite_path)
    return validate_state_config(new_config)


def apply_state_env(
    config: RuntimeStateConfig,
    env: Mapping[str, str],
) -> RuntimeStateConfig:
    """Apply environment overrides to state config.

    Args:
        config: Base state config.
        env: Environment variable mapping.

    Returns:
        State config with environment values applied.
    """
    backend = config.backend
    sqlite_path = config.sqlite_path

    if "IRIS_STATE_BACKEND" in env:
        value = env["IRIS_STATE_BACKEND"]
        backend = validate_backend(value, "IRIS_STATE_BACKEND")

    if "IRIS_STATE_SQLITE_PATH" in env:
        sqlite_path = env["IRIS_STATE_SQLITE_PATH"]

    new_config = replace(config, backend=backend, sqlite_path=sqlite_path)
    return validate_state_config(new_config)
