"""サーバーランタイム設定。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from iris.runtime.config.errors import ConfigError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.runtime.config.parsing import TomlTable


@dataclass(frozen=True)
class RuntimeServerConfig:
    """gRPC サーバーのランタイム設定。"""

    host: str = "127.0.0.1"
    port: int = 50051
    local_only: bool = True
    shutdown_grace_seconds: float = 5.0


_MIN_PORT = 1
_MAX_PORT = 65535


def validate_server_port(value: int, *, source: str) -> int:
    """サーバーポートが有効範囲内であることを検証する。

    Args:
        value: 検証対象のポート番号。
        source: エラーメッセージに含める設定パス。

    Returns:
        int: 検証済みポート番号。

    Raises:
        ConfigError: ポートが有効範囲外の場合。
    """
    if not _MIN_PORT <= value <= _MAX_PORT:
        message = f"Invalid {source}: port must be between {_MIN_PORT} and {_MAX_PORT}: {value}"
        raise ConfigError(message)
    return value


def validate_server_config(config: RuntimeServerConfig) -> RuntimeServerConfig:
    """サーバー設定の制約を検証する。

    ポートが有効であり、``local_only`` がループバックホストを強制していることを確認する。

    Args:
        config: 検証対象のサーバー設定。

    Returns:
        RuntimeServerConfig: 検証済みサーバー設定。

    Raises:
        ConfigError: 設定が制約に違反している場合。
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
    """サーバー設定に TOML テーブルのオーバーライドを適用する。

    Args:
        config: ベースとなるサーバー設定。
        table: ``[server]`` TOML テーブル。

    Returns:
        更新後のサーバー設定。

    Raises:
        ConfigError: 設定値が不正な場合。
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
    """サーバー設定に環境変数を適用する。

    Args:
        config: ベースとなるサーバー設定。
        env: 環境変数のマッピング。

    Returns:
        更新後のサーバー設定。

    Raises:
        ConfigError: 環境変数の値が不正な場合。
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
