"""ランタイム設定向けの汎用 TOML / 環境変数値パースヘルパー。"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING

from iris.runtime.config.errors import ConfigError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from typing import BinaryIO

type TomlScalar = str | int | float | bool | None
type TomlValue = TomlScalar | TomlArray | TomlTable
type TomlArray = list[TomlValue]
type TomlTable = dict[str, TomlValue]

_load_toml: Callable[[BinaryIO], TomlTable] = tomllib.load


def load_toml(file: BinaryIO) -> TomlTable:
    """TOML ドキュメントを、開いているバイナリファイルから読み込む。

    Args:
        file: TOML ドキュメント位置の、開いているバイナリファイルハンドル。

    Returns:
        解析済みトップレベル TOML テーブル。
    """
    return _load_toml(file)


def table_or_empty(table: TomlTable, key: str) -> TomlTable:
    """ネストしたテーブルを返し、存在しない場合は空テーブルを返す。

    Args:
        table: 親 TOML テーブル。
        key: 読み取るネストテーブルキー。

    Returns:
        ネスト TOML テーブル。キーが無い場合は空テーブル。

    Raises:
        ConfigError: 値は存在するがテーブルではない場合。
    """
    value = table.get(key)
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    message = f"Runtime config section '{key}' must be a table"
    raise ConfigError(message)


def parse_string(value: TomlValue, path: str) -> str:
    """必須の文字列 TOML 値をパースする。

    Args:
        value: 検証する TOML 値。
        path: エラーメッセージに使う設定パス。

    Returns:
        検証済み文字列値。

    Raises:
        ConfigError: 値が文字列ではない場合。
    """
    if isinstance(value, str):
        return value
    message = f"Runtime config value '{path}' must be a string"
    raise ConfigError(message)


def parse_optional_string(value: TomlValue, path: str) -> str | None:
    """任意の文字列 TOML 値をパースする。

    Args:
        value: 検証する TOML 値。
        path: エラーメッセージに使う設定パス。

    Returns:
        検証済み文字列値、または ``None``。

    Raises:
        ConfigError: 値が文字列でも null でもない場合。
    """
    if value is None or isinstance(value, str):
        return value
    message = f"Runtime config value '{path}' must be a string or null"
    raise ConfigError(message)


def parse_int(value: TomlValue, path: str) -> int:
    """必須の整数 TOML 値をパースする。

    Args:
        value: 検証する TOML 値。
        path: エラーメッセージに使う設定パス。

    Returns:
        検証済み整数値。

    Raises:
        ConfigError: 値が整数ではない場合。
    """
    if isinstance(value, bool):
        message = f"Runtime config value '{path}' must be an integer"
        raise ConfigError(message)
    if isinstance(value, int):
        return value
    message = f"Runtime config value '{path}' must be an integer"
    raise ConfigError(message)


def parse_optional_int(value: TomlValue, path: str) -> int | None:
    """任意の整数 TOML 値をパースする。

    Args:
        value: 検証する TOML 値。
        path: エラーメッセージに使う設定パス。

    Returns:
        検証済み整数値、または ``None``。
    """
    if value is None:
        return None
    return parse_int(value, path)


def parse_float(value: TomlValue, path: str) -> float:
    """必須の float TOML 値をパースする。

    Args:
        value: 検証する TOML 値。
        path: エラーメッセージに使う設定パス。

    Returns:
        検証済み float 値。

    Raises:
        ConfigError: 値が数値でない場合。
    """
    if isinstance(value, bool):
        message = f"Runtime config value '{path}' must be a float"
        raise ConfigError(message)
    if isinstance(value, (int, float)):
        return float(value)
    message = f"Runtime config value '{path}' must be a float"
    raise ConfigError(message)


def parse_optional_float(value: TomlValue, path: str) -> float | None:
    """任意の float TOML 値をパースする。

    Args:
        value: 検証する TOML 値。
        path: エラーメッセージに使う設定パス。

    Returns:
        検証済み float 値、または ``None``。
    """
    if value is None:
        return None
    return parse_float(value, path)


def env_float(env: Mapping[str, str], key: str, default: float) -> float:
    """必須の float 環境変数を読む。

    Args:
        env: 環境変数マッピング。
        key: 変数名。
        default: 変数が無い場合に返すデフォルト値。

    Returns:
        パース済み float 値、またはデフォルト。

    Raises:
        ConfigError: 値を float として解釈できない場合。
    """
    value = env.get(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        message = f"Environment variable {key} must be a float"
        raise ConfigError(message) from exc


def env_optional_float(env: Mapping[str, str], key: str, default: float | None) -> float | None:
    """任意の float 環境変数を読む。

    Args:
        env: 環境変数マッピング。
        key: 変数名。
        default: 変数が無い場合に返すデフォルト値。

    Returns:
        パース済み float 値、``None``、またはデフォルト。

    Raises:
        ConfigError: 値を float として解釈できない場合。
    """
    value = env.get(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        message = f"Environment variable {key} must be a float"
        raise ConfigError(message) from exc


def env_optional_int(env: Mapping[str, str], key: str, default: int | None) -> int | None:
    """任意の整数環境変数を読む。

    Args:
        env: 環境変数マッピング。
        key: 変数名。
        default: 変数が無い場合に返すデフォルト値。

    Returns:
        パース済み整数値、``None``、またはデフォルト。

    Raises:
        ConfigError: 値を整数として解釈できない場合。
    """
    value = env.get(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        message = f"Environment variable {key} must be an integer"
        raise ConfigError(message) from exc
