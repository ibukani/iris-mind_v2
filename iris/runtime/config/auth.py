"""Runtime RPC auth 設定。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
import os
from typing import TYPE_CHECKING

from iris.runtime.auth.static_tokens import StaticBearerTokenVerifier
from iris.runtime.config.errors import ConfigError
from iris.runtime.config.parsing import parse_bool, parse_string

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.runtime.config.parsing import TomlTable


class RuntimeAuthMode(StrEnum):
    """Runtime RPC auth mode。"""

    LOCAL_DEV = "local_dev"
    REQUIRED = "required"


@dataclass(frozen=True)
class RuntimeAuthConfig:
    """Runtime RPC auth 設定。"""

    mode: RuntimeAuthMode = RuntimeAuthMode.LOCAL_DEV
    allow_unauthenticated_loopback: bool = True
    require_tls_for_remote: bool = True  # Deprecated: TLS is now required for remote bind.
    allow_insecure_remote: bool = False
    static_tokens_env: str = "IRIS_RUNTIME_TOKENS"


def apply_auth_toml(config: RuntimeAuthConfig, table: TomlTable) -> RuntimeAuthConfig:
    """TOML の ``[auth]`` 設定を適用する。

    Returns:
        更新後の auth 設定。
    """
    value = config
    if "mode" in table:
        value = replace(
            value,
            mode=_parse_auth_mode(parse_string(table["mode"], "auth.mode")),
        )
    if "allow_unauthenticated_loopback" in table:
        value = replace(
            value,
            allow_unauthenticated_loopback=parse_bool(
                table["allow_unauthenticated_loopback"],
                "auth.allow_unauthenticated_loopback",
            ),
        )
    if "require_tls_for_remote" in table:
        value = replace(
            value,
            require_tls_for_remote=parse_bool(
                table["require_tls_for_remote"],
                "auth.require_tls_for_remote",
            ),
        )
    if "allow_insecure_remote" in table:
        value = replace(
            value,
            allow_insecure_remote=parse_bool(
                table["allow_insecure_remote"],
                "auth.allow_insecure_remote",
            ),
        )
    if "static_tokens_env" in table:
        value = replace(
            value,
            static_tokens_env=parse_string(
                table["static_tokens_env"],
                "auth.static_tokens_env",
            ),
        )
    return value


def apply_auth_env(
    config: RuntimeAuthConfig,
    env: Mapping[str, str],
) -> RuntimeAuthConfig:
    """Auth 設定の環境変数 override を適用する。

    Returns:
        更新後の auth 設定。
    """
    if "IRIS_RUNTIME_AUTH_MODE" not in env:
        return config
    return replace(
        config,
        mode=_parse_auth_mode(env["IRIS_RUNTIME_AUTH_MODE"]),
    )


def validate_auth_config(
    *,
    auth: RuntimeAuthConfig,
    server_local_only: bool,
    tls_enabled: bool,
) -> RuntimeAuthConfig:
    """Auth と server 公開設定の安全制約を検証する。

    Returns:
        検証済み auth 設定。

    Raises:
        ConfigError: remote bind が安全制約を満たさない場合。
    """
    if server_local_only:
        return auth
    if auth.mode is RuntimeAuthMode.LOCAL_DEV:
        msg = "server.local_only=false requires auth.mode='required'"
        raise ConfigError(msg)
    if not tls_enabled and not auth.allow_insecure_remote:
        msg = (
            "server.local_only=false auth.mode='required' requires TLS "
            "or auth.allow_insecure_remote=true"
        )
        raise ConfigError(msg)
    return auth


def _parse_auth_mode(value: str) -> RuntimeAuthMode:
    try:
        return RuntimeAuthMode(value)
    except ValueError as exc:
        msg = "auth.mode must be one of: local_dev, required"
        raise ConfigError(msg) from exc


def load_token_verifier_from_runtime_env(
    config: RuntimeAuthConfig,
) -> StaticBearerTokenVerifier:
    """os.environ から static bearer token verifier を構築する。

    環境変数の読み取りは config パッケージに限定されているため、
    この関数が唯一の正規エントリポイントとなる。

    Args:
        config: auth 設定。static_tokens_env で env key を決定する。

    Returns:
        StaticBearerTokenVerifier: 構築済み verifier。
    """
    return StaticBearerTokenVerifier.from_env(dict(os.environ), config.static_tokens_env)
