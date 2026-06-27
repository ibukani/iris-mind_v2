"""サーバーランタイム設定。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.parsing import (
    parse_bool,
    parse_float,
    parse_int,
    parse_optional_string,
    parse_string,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.runtime.config.parsing import TomlTable


@dataclass(frozen=True)
class RuntimeServerTlsConfig:
    """gRPC server TLS 設定。"""

    enabled: bool = False
    cert_chain_path: str | None = None
    private_key_path: str | None = None
    client_ca_path: str | None = None
    require_client_cert: bool = False


@dataclass(frozen=True)
class RuntimeServerConfig:
    """gRPC サーバーのランタイム設定。"""

    host: str = "127.0.0.1"
    port: int = 50051
    local_only: bool = True
    shutdown_grace_seconds: float = 5.0
    tls: RuntimeServerTlsConfig = RuntimeServerTlsConfig()


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
    if config.tls.enabled and (not config.tls.cert_chain_path or not config.tls.private_key_path):
        message = "server.tls.enabled=true requires cert_chain_path and private_key_path"
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
        host = parse_string(table["host"], "server.host")

    port = config.port
    if "port" in table:
        port = parse_int(table["port"], "server.port")
        port = validate_server_port(port, source="server.port")

    local_only = _local_only_from_toml(default=config.local_only, table=table)

    shutdown_grace = config.shutdown_grace_seconds
    if "shutdown_grace_seconds" in table:
        shutdown_grace = parse_float(
            table["shutdown_grace_seconds"],
            "server.shutdown_grace_seconds",
        )
        if shutdown_grace < 0:
            message = "server.shutdown_grace_seconds must be zero or greater"
            raise ConfigError(message)

    tls = config.tls
    if "tls" in table:
        tls_table = table["tls"]
        if not isinstance(tls_table, dict):
            message = "server.tls must be a table"
            raise ConfigError(message)
        tls = _apply_tls_toml(tls, tls_table)

    return replace(
        config,
        host=host,
        port=port,
        local_only=local_only,
        shutdown_grace_seconds=shutdown_grace,
        tls=tls,
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


def _local_only_from_toml(*, default: bool, table: TomlTable) -> bool:
    """server.local_only TOML 値を取り出す。

    Returns:
        更新後の local_only 値。
    """
    if "local_only" not in table:
        return default
    return parse_bool(table["local_only"], "server.local_only")


def _apply_tls_toml(
    config: RuntimeServerTlsConfig,
    table: TomlTable,
) -> RuntimeServerTlsConfig:
    """TOML の ``[server.tls]`` 設定を適用する。

    Returns:
        更新後の TLS 設定。
    """
    value = config
    if "enabled" in table:
        value = replace(
            value,
            enabled=parse_bool(table["enabled"], "server.tls.enabled"),
        )
    if "cert_chain_path" in table:
        value = replace(
            value,
            cert_chain_path=parse_optional_string(
                table["cert_chain_path"],
                "server.tls.cert_chain_path",
            ),
        )
    if "private_key_path" in table:
        value = replace(
            value,
            private_key_path=parse_optional_string(
                table["private_key_path"],
                "server.tls.private_key_path",
            ),
        )
    if "client_ca_path" in table:
        value = replace(
            value,
            client_ca_path=parse_optional_string(
                table["client_ca_path"],
                "server.tls.client_ca_path",
            ),
        )
    if "require_client_cert" in table:
        value = replace(
            value,
            require_client_cert=parse_bool(
                table["require_client_cert"],
                "server.tls.require_client_cert",
            ),
        )
    return value
