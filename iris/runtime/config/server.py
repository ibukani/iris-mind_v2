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

    local_only = config.local_only
    if "local_only" in table:
        local_only = bool(table["local_only"])

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

    return replace(config, host=host, port=port)
