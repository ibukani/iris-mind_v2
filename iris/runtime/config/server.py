"""Server runtime configuration."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from iris.runtime.config.errors import ConfigError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.runtime.config.parsing import TomlTable


@dataclass(frozen=True)
class RuntimeServerConfig:
    """gRPC Server runtime configuration."""

    host: str = "127.0.0.1"
    port: int = 50051
    local_only: bool = True
    shutdown_grace_seconds: float = 5.0


_MIN_PORT = 1
_MAX_PORT = 65535


def validate_server_port(value: int, *, source: str) -> int:
    """Validate that a server port is within the valid range.

    Args:
        value: Port number to validate.
        source: Configuration path for error messages.

    Returns:
        int: The validated port number.

    Raises:
        ConfigError: If the port is out of valid bounds.
    """
    if not _MIN_PORT <= value <= _MAX_PORT:
        message = f"Invalid {source}: port must be between {_MIN_PORT} and {_MAX_PORT}: {value}"
        raise ConfigError(message)
    return value


def validate_server_config(config: RuntimeServerConfig) -> RuntimeServerConfig:
    """Validate server configuration constraints.

    Ensures port is valid and local_only enforces loopback host.

    Args:
        config: Server config to validate.

    Returns:
        RuntimeServerConfig: Validated server config.

    Raises:
        ConfigError: If config violates constraints.
    """
    validate_server_port(config.port, source="server.port")
    if config.local_only and config.host not in {"127.0.0.1", "localhost", "::1"}:
        message = f"server.local_only=true requires a loopback host, got: {config.host}"
        raise ConfigError(message)
    return config


def apply_server_toml(
    config: RuntimeServerConfig,
    table: TomlTable,
) -> RuntimeServerConfig:
    """Apply TOML table overrides to the server config.

    Args:
        config: Base server config.
        table: The [server] TOML table.

    Returns:
        Updated server config.

    Raises:
        ConfigError: If config values are invalid.
    """
    host = config.host
    if "host" in table:
        host = str(table["host"])

    port = config.port
    if "port" in table:
        try:
            port = int(str(table["port"]))
        except (ValueError, TypeError) as err:
            message = f"Invalid server port: {table['port']}"
            raise ConfigError(message) from err
        port = validate_server_port(port, source="server.port")

    local_only = config.local_only
    if "local_only" in table:
        value = table["local_only"]
        if not isinstance(value, bool):
            message = "server.local_only must be a boolean"
            raise ConfigError(message)
        local_only = value

    shutdown_grace = config.shutdown_grace_seconds
    if "shutdown_grace_seconds" in table:
        try:
            shutdown_grace = float(str(table["shutdown_grace_seconds"]))
        except (ValueError, TypeError) as err:
            message = f"Invalid server shutdown_grace_seconds: {table['shutdown_grace_seconds']}"
            raise ConfigError(message) from err

    return replace(
        config,
        host=host,
        port=port,
        local_only=local_only,
        shutdown_grace_seconds=shutdown_grace,
    )


def apply_server_env(
    config: RuntimeServerConfig,
    env: Mapping[str, str],
) -> RuntimeServerConfig:
    """Apply environment variables to the server config.

    Args:
        config: Base server config.
        env: Environment variable mapping.

    Returns:
        Updated server config.

    Raises:
        ConfigError: If env values are invalid.
    """
    host = config.host
    if "IRIS_SERVER_HOST" in env:
        host = env["IRIS_SERVER_HOST"]

    port = config.port
    if "IRIS_SERVER_PORT" in env:
        try:
            port = int(env["IRIS_SERVER_PORT"])
        except ValueError as err:
            message = f"Invalid IRIS_SERVER_PORT: {env['IRIS_SERVER_PORT']}"
            raise ConfigError(message) from err
        port = validate_server_port(port, source="IRIS_SERVER_PORT")

    return replace(config, host=host, port=port)
