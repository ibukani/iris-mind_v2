"""ランタイム状態の永続化設定。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.parsing import parse_string

if TYPE_CHECKING:
    from iris.runtime.config.parsing import TomlTable


class RuntimeStateBackend(StrEnum):
    """ランタイムstateバックエンド。"""

    MEMORY = "memory"
    SQLITE = "sqlite"


@dataclass(frozen=True)
class RuntimeStateConfig:
    """永続状態とストレージの設定。"""

    backend: RuntimeStateBackend = RuntimeStateBackend.MEMORY
    sqlite_path: str = ".iris/runtime/state.sqlite3"


def validate_backend(value: str, path: str) -> RuntimeStateBackend:
    """バックエンド名を検証する。

    Args:
        value: 検証対象のバックエンド名。
        path: エラーメッセージに含める設定パス。

    Returns:
        RuntimeStateBackend: 検証済みバックエンド名。

    Raises:
        ConfigError: バックエンド名が不正な場合。
    """
    try:
        return RuntimeStateBackend(value)
    except ValueError as exc:
        message = f"Invalid {path}: {value}"
        raise ConfigError(message) from exc


def validate_state_config(config: RuntimeStateConfig) -> RuntimeStateConfig:
    """状態設定の制約を検証する。

    Args:
        config: 検証対象の状態設定。

    Returns:
        RuntimeStateConfig: 検証済みの設定。

    Raises:
        ConfigError: 制約に違反している場合。
    """
    if config.backend == RuntimeStateBackend.SQLITE and not config.sqlite_path:
        message = "state.sqlite_path must be non-empty when backend is sqlite"
        raise ConfigError(message)
    return config


def apply_state_toml(config: RuntimeStateConfig, table: TomlTable) -> RuntimeStateConfig:
    """状態設定に TOML オーバーライドを適用する。

    Args:
        config: ベースとなる状態設定。
        table: 解析済みの状態用 TOML テーブル。

    Returns:
        TOML 値を反映した状態設定。
    """
    value = config
    if "backend" in table:
        value = replace(
            value,
            backend=validate_backend(
                parse_string(table["backend"], "state.backend"),
                "state.backend in TOML",
            ),
        )
    if "sqlite_path" in table:
        value = replace(
            value,
            sqlite_path=parse_string(table["sqlite_path"], "state.sqlite_path"),
        )
    return validate_state_config(value)


def apply_state_env(
    config: RuntimeStateConfig,
    env: Mapping[str, str],
) -> RuntimeStateConfig:
    """状態設定に環境変数オーバーライドを適用する。

    Args:
        config: ベースとなる状態設定。
        env: 環境変数のマッピング。

    Returns:
        環境変数値を反映した状態設定。
    """
    value = config
    if "IRIS_STATE_BACKEND" in env:
        value = replace(
            value,
            backend=validate_backend(env["IRIS_STATE_BACKEND"], "IRIS_STATE_BACKEND"),
        )
    if "IRIS_STATE_SQLITE_PATH" in env:
        value = replace(value, sqlite_path=env["IRIS_STATE_SQLITE_PATH"])
    return validate_state_config(value)
