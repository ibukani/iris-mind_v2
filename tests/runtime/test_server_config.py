"""Tests for runtime server config."""

from __future__ import annotations

import pytest

from iris.runtime.config import RuntimeConfigOverrides
from iris.runtime.config.errors import ConfigError
from iris.runtime.config.root import apply_runtime_overrides, default_runtime_config
from iris.runtime.config.server import (
    RuntimeServerConfig,
    RuntimeServerTlsConfig,
    apply_server_env,
    apply_server_toml,
    validate_server_config,
)
from tests.helpers.toml import toml_table


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
    table = toml_table(
        host="127.0.0.2",
        port=8080,
        local_only=False,
        shutdown_grace_seconds=10.5,
    )
    updated = apply_server_toml(config, table)
    assert updated.host == "127.0.0.2"
    assert updated.port == 8080
    assert updated.local_only is False
    assert abs(updated.shutdown_grace_seconds - 10.5) < 0.001


def test_apply_server_toml_clears_optional_tls_paths() -> None:
    """明示的な null は既存の optional TLS path を解除する。"""
    config = RuntimeServerConfig(
        tls=RuntimeServerTlsConfig(
            cert_chain_path="server.crt",
            private_key_path="server.key",
            client_ca_path="client-ca.crt",
        ),
    )

    updated = apply_server_toml(
        config,
        toml_table(
            tls={
                "cert_chain_path": None,
                "private_key_path": None,
                "client_ca_path": None,
            },
        ),
    )

    assert updated.tls.cert_chain_path is None
    assert updated.tls.private_key_path is None
    assert updated.tls.client_ca_path is None


def test_apply_server_toml_invalid_port() -> None:
    """Invalid port in TOML raises ConfigError."""
    config = RuntimeServerConfig()
    table = toml_table(port="not-an-int")
    with pytest.raises(ConfigError):
        apply_server_toml(config, table)


def test_apply_server_toml_invalid_grace() -> None:
    """Invalid shutdown_grace_seconds in TOML raises ConfigError."""
    config = RuntimeServerConfig()
    table = toml_table(shutdown_grace_seconds="not-a-float")
    with pytest.raises(ConfigError):
        apply_server_toml(config, table)


def test_apply_server_toml_rejects_non_loopback_host_when_local_only() -> None:
    """apply_server_toml enforces the loopback constraint."""
    config = RuntimeServerConfig()
    table = toml_table(host="10.0.0.1")
    with pytest.raises(ConfigError, match="requires a loopback host"):
        apply_server_toml(config, table)


def test_apply_server_env_valid() -> None:
    """Server config can be updated via ENV variables."""
    config = RuntimeServerConfig()
    env = {
        "IRIS_SERVER_HOST": "127.0.0.1",
        "IRIS_SERVER_PORT": "9090",
    }
    updated = apply_server_env(config, env)
    assert updated.host == "127.0.0.1"
    assert updated.port == 9090


def test_apply_server_env_invalid_port() -> None:
    """Invalid port in ENV raises ConfigError."""
    config = RuntimeServerConfig()
    env = {"IRIS_SERVER_PORT": "not-an-int"}
    with pytest.raises(ConfigError):
        apply_server_env(config, env)


def test_apply_server_env_rejects_non_loopback_host_when_local_only() -> None:
    """apply_server_env enforces the loopback constraint."""
    config = RuntimeServerConfig()
    env = {"IRIS_SERVER_HOST": "10.0.0.1"}
    with pytest.raises(ConfigError, match="requires a loopback host"):
        apply_server_env(config, env)


def test_validate_server_port_bounds() -> None:
    """Server port validation enforces bounds."""
    config = RuntimeServerConfig()

    # 0 is invalid
    with pytest.raises(ConfigError):
        apply_server_toml(config, toml_table(port=0))

    with pytest.raises(ConfigError):
        apply_server_env(config, {"IRIS_SERVER_PORT": "0"})

    # 65536 is invalid
    with pytest.raises(ConfigError):
        apply_server_toml(config, toml_table(port=65536))

    # overrides
    with pytest.raises(ConfigError):
        apply_runtime_overrides(default_runtime_config(), RuntimeConfigOverrides(server_port=0))


def test_apply_runtime_overrides_rejects_non_loopback_server_host() -> None:
    """CLI server host override must still respect local_only."""
    with pytest.raises(ConfigError, match="requires a loopback host"):
        apply_runtime_overrides(
            default_runtime_config(),
            RuntimeConfigOverrides(server_host="10.0.0.1"),
        )


def test_apply_runtime_overrides_accepts_loopback_server_host() -> None:
    """CLI server host override accepts loopback hosts."""
    config = apply_runtime_overrides(
        default_runtime_config(),
        RuntimeConfigOverrides(server_host="127.0.0.1"),
    )

    assert config.server.host == "127.0.0.1"


def test_validate_local_only() -> None:
    """local_only=True requires a loopback host."""
    # Invalid
    config = RuntimeServerConfig(local_only=True, host="10.0.0.1")
    with pytest.raises(ConfigError, match="requires a loopback host"):
        validate_server_config(config)

    # Valid loopback
    config = RuntimeServerConfig(local_only=True, host="127.0.0.1")
    validate_server_config(config)

    # Valid non-local
    config = RuntimeServerConfig(local_only=False, host="10.0.0.1")
    validate_server_config(config)


def test_validate_server_config_rejects_negative_grace_seconds() -> None:
    """validate_server_config は負の grace 秒数を拒否する。"""
    config = RuntimeServerConfig(shutdown_grace_seconds=-1.0)
    with pytest.raises(ConfigError, match="must be zero or greater"):
        validate_server_config(config)


def test_apply_server_toml_strict_bool() -> None:
    """TOML parser strictly requires boolean for local_only."""
    config = RuntimeServerConfig()
    table = toml_table(local_only="false")
    with pytest.raises(ConfigError, match="must be a boolean"):
        apply_server_toml(config, table)
