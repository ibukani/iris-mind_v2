"""ランタイム状態の永続化設定。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Mapping

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.parsing import parse_string

if TYPE_CHECKING:
    from iris.runtime.config.parsing import TomlTable


@dataclass(frozen=True)
class RuntimeStateConfig:
    """永続状態とストレージの設定。"""

    backend: Literal["memory", "sqlite"] = "memory"
    sqlite_path: str = ".iris/runtime/state.sqlite3"


_VALID_BACKENDS: tuple[Literal["memory", "sqlite"], ...] = ("memory", "sqlite")


def validate_backend(value: str, path: str) -> Literal["memory", "sqlite"]:
    """バックエンド名を検証し、型付きリテラルを返す。

    Args:
        value: 検証対象のバックエンド名。
        path: エラーメッセージに含める設定パス。

    Returns:
        Literal["memory", "sqlite"]: 検証済みバックエンド名。

    Raises:
        ConfigError: バックエンド名が不正な場合。
    """
    if value in _VALID_BACKENDS:
        return value
    message = f"Invalid {path}: {value}"
    raise ConfigError(message)


def validate_state_config(config: RuntimeStateConfig) -> RuntimeStateConfig:
    """状態設定の制約を検証する。

    Args:
        config: 検証対象の状態設定。

    Returns:
        RuntimeStateConfig: 検証済みの設定。

    Raises:
        ConfigError: 制約に違反している場合。
    """
    if config.backend not in {"memory", "sqlite"}:
        message = f"Invalid state.backend: {config.backend}"
        raise ConfigError(message)
    if config.backend == "sqlite" and not config.sqlite_path:
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
    backend = config.backend
    sqlite_path = config.sqlite_path

    if "backend" in table:
        value = parse_string(table["backend"], "state.backend")
        backend = validate_backend(value, "state.backend in TOML")

    if "sqlite_path" in table:
        sqlite_path = parse_string(table["sqlite_path"], "state.sqlite_path")

    new_config = replace(config, backend=backend, sqlite_path=sqlite_path)
    return validate_state_config(new_config)


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
    backend = config.backend
    sqlite_path = config.sqlite_path

    if "IRIS_STATE_BACKEND" in env:
        value = env["IRIS_STATE_BACKEND"]
        backend = validate_backend(value, "IRIS_STATE_BACKEND")

    if "IRIS_STATE_SQLITE_PATH" in env:
        sqlite_path = env["IRIS_STATE_SQLITE_PATH"]

    new_config = replace(config, backend=backend, sqlite_path=sqlite_path)
    return validate_state_config(new_config)
