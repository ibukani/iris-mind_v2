"""Tests for state configuration."""

from __future__ import annotations

import pytest

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.state import (
    RuntimeStateBackend,
    RuntimeStateConfig,
    apply_state_env,
    apply_state_toml,
)
from tests.helpers.toml import toml_table


def test_state_config_defaults() -> None:
    """Test state config default values."""
    config = RuntimeStateConfig()
    assert config.backend == RuntimeStateBackend.MEMORY
    assert config.sqlite_path == ".iris/runtime/state.sqlite3"


def test_apply_state_toml_valid() -> None:
    """Test apply_state_toml with valid backend."""
    config = RuntimeStateConfig()
    table = toml_table(backend="sqlite", sqlite_path="test.db")
    new_config = apply_state_toml(config, table)
    assert new_config.backend == RuntimeStateBackend.SQLITE
    assert new_config.sqlite_path == "test.db"


def test_apply_state_toml_invalid_backend() -> None:
    """Test apply_state_toml rejects invalid backend."""
    config = RuntimeStateConfig()
    table = toml_table(backend="postgres")
    with pytest.raises(ConfigError, match=r"Invalid state\.backend"):
        apply_state_toml(config, table)


def test_apply_state_toml_empty_sqlite_path() -> None:
    """Test apply_state_toml rejects empty sqlite path."""
    config = RuntimeStateConfig()
    table = toml_table(backend="sqlite", sqlite_path="")
    with pytest.raises(ConfigError, match="must be non-empty"):
        apply_state_toml(config, table)


def test_apply_state_env_valid() -> None:
    """Test apply_state_env with valid values."""
    config = RuntimeStateConfig()
    env = {"IRIS_STATE_BACKEND": "sqlite", "IRIS_STATE_SQLITE_PATH": "env.db"}
    new_config = apply_state_env(config, env)
    assert new_config.backend == RuntimeStateBackend.SQLITE
    assert new_config.sqlite_path == "env.db"


def test_apply_state_env_invalid_backend() -> None:
    """Test apply_state_env rejects invalid backend."""
    config = RuntimeStateConfig()
    env = {"IRIS_STATE_BACKEND": "postgres"}
    with pytest.raises(ConfigError, match="Invalid IRIS_STATE_BACKEND"):
        apply_state_env(config, env)
