"""Tests for runtime server config."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.server import (
    RuntimeServerConfig,
    apply_server_env,
    apply_server_toml,
)

if TYPE_CHECKING:
    from iris.runtime.config.parsing import TomlTable


def test_default_server_config() -> None:
    """Default server config values are correct."""
    config = RuntimeServerConfig()
    assert config.host == "127.0.0.1"
    assert config.port == 50051
    assert config.local_only is True
    assert abs(config.shutdown_grace_seconds - 5.0) < 0.001


def test_apply_server_toml_valid() -> None:
    """Server config can be updated via TOML."""
    config = RuntimeServerConfig()
    table = {
        "server": {
            "host": "127.0.0.2",
            "port": 8080,
            "local_only": False,
            "shutdown_grace_seconds": 10.5,
        }
    }
    updated = apply_server_toml(config, cast("TomlTable", table["server"]))
    assert updated.host == "127.0.0.2"
    assert updated.port == 8080
    assert updated.local_only is False
    assert abs(updated.shutdown_grace_seconds - 10.5) < 0.001


def test_apply_server_toml_invalid_port() -> None:
    """Invalid port in TOML raises ConfigError."""
    config = RuntimeServerConfig()
    table = {"port": "not-an-int"}
    with pytest.raises(ConfigError):
        apply_server_toml(config, cast("TomlTable", table))


def test_apply_server_toml_invalid_grace() -> None:
    """Invalid shutdown_grace_seconds in TOML raises ConfigError."""
    config = RuntimeServerConfig()
    table = {"shutdown_grace_seconds": "not-a-float"}
    with pytest.raises(ConfigError):
        apply_server_toml(config, cast("TomlTable", table))


def test_apply_server_env_valid() -> None:
    """Server config can be updated via ENV variables."""
    config = RuntimeServerConfig()
    env = {
        "IRIS_SERVER_HOST": "127.0.0.2",
        "IRIS_SERVER_PORT": "9090",
    }
    updated = apply_server_env(config, env)
    assert updated.host == "127.0.0.2"
    assert updated.port == 9090


def test_apply_server_env_invalid_port() -> None:
    """Invalid port in ENV raises ConfigError."""
    config = RuntimeServerConfig()
    env = {"IRIS_SERVER_PORT": "not-an-int"}
    with pytest.raises(ConfigError):
        apply_server_env(config, env)


def test_validate_server_port_bounds() -> None:
    """Server port validation enforces bounds."""
    from iris.runtime.config import RuntimeConfigOverrides
    from iris.runtime.config.root import apply_runtime_overrides, default_runtime_config
    from iris.runtime.config.server import RuntimeServerConfig, apply_server_env, apply_server_toml

    config = RuntimeServerConfig()

    # 0 is invalid
    with pytest.raises(ConfigError):
        apply_server_toml(config, cast("TomlTable", {"port": 0}))

    with pytest.raises(ConfigError):
        apply_server_env(config, {"IRIS_SERVER_PORT": "0"})

    # 65536 is invalid
    with pytest.raises(ConfigError):
        apply_server_toml(config, cast("TomlTable", {"port": 65536}))

    # overrides
    with pytest.raises(ConfigError):
        apply_runtime_overrides(default_runtime_config(), RuntimeConfigOverrides(server_port=0))


def test_validate_local_only() -> None:
    """local_only=True requires a loopback host."""
    from iris.runtime.config.server import RuntimeServerConfig, validate_server_config

    # Invalid
    config = RuntimeServerConfig(local_only=True, host="0.0.0.0")
    with pytest.raises(ConfigError, match="requires a loopback host"):
        validate_server_config(config)

    # Valid loopback
    config = RuntimeServerConfig(local_only=True, host="127.0.0.1")
    validate_server_config(config)

    # Valid non-local
    config = RuntimeServerConfig(local_only=False, host="0.0.0.0")
    validate_server_config(config)


def test_apply_server_toml_strict_bool() -> None:
    """TOML parser strictly requires boolean for local_only."""
    from iris.runtime.config.server import RuntimeServerConfig, apply_server_toml

    config = RuntimeServerConfig()
    table = {"local_only": "false"}
    with pytest.raises(ConfigError, match="must be a boolean"):
        apply_server_toml(config, cast("TomlTable", table))
