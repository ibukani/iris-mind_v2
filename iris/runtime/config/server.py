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
    table_or_empty,
)
from iris.runtime.config.validation import require_zero_or_greater

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
    """
    validate_server_port(config.port, source="server.port")
    _validate_loopback_host(config)
    return replace(
        config,
        shutdown_grace_seconds=require_zero_or_greater(
            config.shutdown_grace_seconds,
            "server.shutdown_grace_seconds",
        ),
        tls=_validate_tls_config(config.tls),
    )


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
    """
    return _ServerConfigPatch.from_table(table).apply(config)


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
    """
    return _ServerConfigPatch.from_env(env).apply(config)


def _validate_loopback_host(config: RuntimeServerConfig) -> RuntimeServerConfig:
    """local_only と host の組を検証する。

    Args:
        config: 検証対象のサーバー設定。

    Returns:
        検証済みのサーバー設定。

    Raises:
        ConfigError: local_only が有効なのに host が loopback でない場合。
    """
    if config.local_only and config.host not in {"127.0.0.1", "localhost", "::1"}:
        message = f"server.local_only=true requires a loopback host, got: {config.host}"
        raise ConfigError(message)
    return config


def _validate_tls_config(config: RuntimeServerTlsConfig) -> RuntimeServerTlsConfig:
    """TLS 設定の必須フィールドを検証する。

    Args:
        config: 検証対象の TLS 設定。

    Returns:
        検証済みの TLS 設定。

    Raises:
        ConfigError: enabled が true なのに必須 path がない場合。
    """
    if config.enabled and (not config.cert_chain_path or not config.private_key_path):
        message = "server.tls.enabled=true requires cert_chain_path and private_key_path"
        raise ConfigError(message)
    return config


def _parse_env_int(env: Mapping[str, str], key: str) -> int | None:
    """環境変数の整数 override を解析する。

    Returns:
        解析済みの整数。key が無い場合は None。

    Raises:
        ConfigError: 整数として解釈できない場合。
    """
    if key not in env:
        return None
    try:
        return int(env[key])
    except ValueError as err:
        message = f"Invalid {key}: {env[key]}"
        raise ConfigError(message) from err


@dataclass(frozen=True)
class _ServerTlsPatch:
    """server.tls の optional 更新値を束ねる。"""

    enabled: bool | None = None
    cert_chain_path: str | None = None
    cert_chain_path_set: bool = False
    private_key_path: str | None = None
    private_key_path_set: bool = False
    client_ca_path: str | None = None
    client_ca_path_set: bool = False
    require_client_cert: bool | None = None

    @classmethod
    def from_table(cls, table: TomlTable) -> _ServerTlsPatch:
        """TOML テーブルから TLS patch を組み立てる。

        Returns:
            組み立てた TLS patch。
        """
        return cls(
            enabled=parse_bool(table["enabled"], "server.tls.enabled")
            if "enabled" in table
            else None,
            cert_chain_path=parse_optional_string(
                table["cert_chain_path"],
                "server.tls.cert_chain_path",
            )
            if "cert_chain_path" in table
            else None,
            cert_chain_path_set="cert_chain_path" in table,
            private_key_path=parse_optional_string(
                table["private_key_path"],
                "server.tls.private_key_path",
            )
            if "private_key_path" in table
            else None,
            private_key_path_set="private_key_path" in table,
            client_ca_path=parse_optional_string(
                table["client_ca_path"],
                "server.tls.client_ca_path",
            )
            if "client_ca_path" in table
            else None,
            client_ca_path_set="client_ca_path" in table,
            require_client_cert=parse_bool(
                table["require_client_cert"],
                "server.tls.require_client_cert",
            )
            if "require_client_cert" in table
            else None,
        )

    def apply(self, config: RuntimeServerTlsConfig) -> RuntimeServerTlsConfig:
        """TLS 設定へ patch を適用する。

        Returns:
            更新後の TLS 設定。
        """
        value = config
        if self.enabled is not None:
            value = replace(value, enabled=self.enabled)
        if self.cert_chain_path_set:
            value = replace(value, cert_chain_path=self.cert_chain_path)
        if self.private_key_path_set:
            value = replace(value, private_key_path=self.private_key_path)
        if self.client_ca_path_set:
            value = replace(value, client_ca_path=self.client_ca_path)
        if self.require_client_cert is not None:
            value = replace(value, require_client_cert=self.require_client_cert)
        return _validate_tls_config(value)


@dataclass(frozen=True)
class _ServerConfigPatch:
    """server の optional 更新値を束ねる。"""

    host: str | None = None
    port: int | None = None
    local_only: bool | None = None
    shutdown_grace_seconds: float | None = None
    tls: _ServerTlsPatch | None = None

    @classmethod
    def from_table(cls, table: TomlTable) -> _ServerConfigPatch:
        """TOML テーブルから server patch を組み立てる。

        Returns:
            組み立てた server patch。
        """
        return cls(
            host=parse_string(table["host"], "server.host") if "host" in table else None,
            port=parse_int(table["port"], "server.port") if "port" in table else None,
            local_only=(
                parse_bool(table["local_only"], "server.local_only")
                if "local_only" in table
                else None
            ),
            shutdown_grace_seconds=(
                parse_float(
                    table["shutdown_grace_seconds"],
                    "server.shutdown_grace_seconds",
                )
                if "shutdown_grace_seconds" in table
                else None
            ),
            tls=_ServerTlsPatch.from_table(
                table_or_empty(table, "tls", path="server.tls"),
            ),
        )

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> _ServerConfigPatch:
        """環境変数から server patch を組み立てる。

        Returns:
            組み立てた server patch。
        """
        return cls(
            host=env.get("IRIS_SERVER_HOST", None),
            port=_parse_env_int(env, "IRIS_SERVER_PORT"),
        )

    def apply(self, config: RuntimeServerConfig) -> RuntimeServerConfig:
        """Server 設定へ patch を適用して検証する。

        Returns:
            検証済みの server 設定。
        """
        value = config
        if self.host is not None:
            value = replace(value, host=self.host)
        if self.port is not None:
            value = replace(value, port=self.port)
        if self.local_only is not None:
            value = replace(value, local_only=self.local_only)
        if self.shutdown_grace_seconds is not None:
            value = replace(
                value,
                shutdown_grace_seconds=require_zero_or_greater(
                    self.shutdown_grace_seconds,
                    "server.shutdown_grace_seconds",
                ),
            )
        if self.tls is not None:
            value = replace(value, tls=self.tls.apply(value.tls))
        return validate_server_config(value)
