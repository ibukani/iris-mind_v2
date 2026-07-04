"""ランタイム設定向けの汎用 TOML / 環境変数値パースヘルパー。"""

from __future__ import annotations

import difflib
import tomllib
from typing import TYPE_CHECKING

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.spec import ConfigFieldSpec, runtime_config_specs_for_version

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from typing import BinaryIO

type TomlScalar = str | int | float | bool | None
type TomlValue = TomlScalar | TomlArray | TomlTable
type TomlArray = list[TomlValue]
type TomlTable = dict[str, TomlValue]

_load_toml: Callable[[BinaryIO], TomlTable] = tomllib.load


def _type_error_message(path: str, expected: str) -> str:
    """型不一致の統一エラーメッセージを生成する。

    Args:
        path: エラーメッセージに使う設定パス。
        expected: 期待される型の説明文字列。

    Returns:
        フォーマット済みエラーメッセージ。
    """
    return f"Runtime config value '{path}' must be {expected}"


def _env_type_error_message(key: str, expected: str) -> str:
    """環境変数の型不一致統一エラーメッセージを生成する。

    Args:
        key: 環境変数名。
        expected: 期待される型の説明文字列。

    Returns:
        フォーマット済みエラーメッセージ。
    """
    return f"Environment variable {key} must be {expected}"


def load_toml(file: BinaryIO) -> TomlTable:
    """TOML ドキュメントを、開いているバイナリファイルから読み込む。

    Args:
        file: TOML ドキュメント位置の、開いているバイナリファイルハンドル。

    Returns:
        解析済みトップレベル TOML テーブル。
    """
    return _load_toml(file)


def table_or_empty(
    table: TomlTable,
    key: str,
    *,
    path: str | None = None,
) -> TomlTable:
    """ネストしたテーブルを返し、存在しない場合は空テーブルを返す。

    Args:
        table: 親 TOML テーブル。
        key: 読み取るネストテーブルキー。
        path: 型エラーに含める任意の完全な設定パス。

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
    message = (
        f"{path} must be a table"
        if path is not None
        else f"Runtime config section '{key}' must be a table"
    )
    raise ConfigError(message)


def validate_toml_keys(
    table: TomlTable,
    *,
    source: str,
    specs: tuple[ConfigFieldSpec, ...],
) -> None:
    """TOMLの全keyがConfigSpecに存在することを検証する。

    Args:
        table: 検証するトップレベルTOMLテーブル。
        source: エラーに含める設定ファイルパス。
        specs: 検証対象versionの設定フィールド仕様。

    """
    allowed_paths = frozenset(spec.path for spec in specs if spec.toml)
    section_paths = frozenset(
        ".".join(parts[:index])
        for path in allowed_paths
        for parts in (path.split("."),)
        for index in range(1, len(parts))
    )
    _validate_table_keys(table, "", allowed_paths, section_paths, source)


def _validate_table_keys(
    table: TomlTable,
    prefix: str,
    allowed_paths: frozenset[str],
    section_paths: frozenset[str],
    source: str,
) -> None:
    for key, value in table.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            if path not in section_paths:
                _raise_unknown_key(path, allowed_paths, source)
            _validate_table_keys(value, path, allowed_paths, section_paths, source)
        elif path not in allowed_paths:
            _raise_unknown_key(path, allowed_paths, source)


def _raise_unknown_key(path: str, allowed_paths: frozenset[str], source: str) -> None:
    suggestion = difflib.get_close_matches(path, allowed_paths, n=1)
    suffix = f" Did you mean: {suggestion[0]}?" if suggestion else ""
    message = f"Unknown runtime config key in {source}: {path}.{suffix}"
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
    raise ConfigError(_type_error_message(path, "a string"))


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
    raise ConfigError(_type_error_message(path, "a string or null"))


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
        raise ConfigError(_type_error_message(path, "an integer"))
    if isinstance(value, int):
        return value
    raise ConfigError(_type_error_message(path, "an integer"))


def parse_raw_config_version(table: TomlTable) -> int:
    """Raw TOMLからconfig versionを読み、対応schemaがあることを検証する。

    Args:
        table: key検証前のトップレベルTOMLテーブル。

    Returns:
        検証済みconfig version。省略時は後方互換として1。
    """
    config_table = table_or_empty(table, "config")
    version = 2
    if "version" in config_table:
        version = parse_int(config_table["version"], "config.version")
    runtime_config_specs_for_version(version)
    return version


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
        raise ConfigError(_type_error_message(path, "a float"))
    if isinstance(value, (int, float)):
        return float(value)
    raise ConfigError(_type_error_message(path, "a float"))


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


def parse_bool(value: TomlValue, path: str) -> bool:
    """必須の真偽値 TOML 値をパースする。

    Args:
        value: 検証する TOML 値。
        path: エラーメッセージに使う設定パス。

    Returns:
        検証済み真偽値。

    Raises:
        ConfigError: 値が真偽値ではない場合。
    """
    if isinstance(value, bool):
        return value
    raise ConfigError(_type_error_message(path, "a boolean"))


def env_bool(env: Mapping[str, str], key: str, *, default: bool) -> bool:
    """必須の真偽値環境変数を読む。

    Args:
        env: 環境変数マッピング。
        key: 変数名。
        default: 変数が無い場合に返すデフォルト値。

    Returns:
        パース済み真偽値、またはデフォルト。

    Raises:
        ConfigError: 値を真偽値として解釈できない場合。
    """
    value = env.get(key)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(_env_type_error_message(key, "a boolean (true/false, 1/0, yes/no, on/off)"))


def _env_parse[T, D](
    env: Mapping[str, str],
    key: str,
    default: D,
    parser: Callable[[str], T],
    expected: str,
) -> T | D:
    """環境変数を共通パターンで読み込む。

    Args:
        env: 環境変数マッピング。
        key: 変数名。
        default: 変数が無い場合に返すデフォルト値。
        parser: 値を変換する callable (float または int)。
        expected: エラーメッセージに使う型名。

    Returns:
        パース済み値、またはデフォルト。

    Raises:
        ConfigError: 値を期待型として解釈できない場合。
    """
    value = env.get(key)
    if value is None:
        return default
    try:
        return parser(value)
    except ValueError as exc:
        raise ConfigError(_env_type_error_message(key, expected)) from exc


def env_float(env: Mapping[str, str], key: str, default: float) -> float:
    """必須の float 環境変数を読む。

    Args:
        env: 環境変数マッピング。
        key: 変数名。
        default: 変数が無い場合に返すデフォルト値。

    Returns:
        パース済み float 値、またはデフォルト。
    """
    return _env_parse(env, key, default, float, "a float")


def env_optional_float(env: Mapping[str, str], key: str, default: float | None) -> float | None:
    """任意の float 環境変数を読む。

    Args:
        env: 環境変数マッピング。
        key: 変数名。
        default: 変数が無い場合に返すデフォルト値。

    Returns:
        パース済み float 値、``None``、またはデフォルト。
    """
    return _env_parse(env, key, default, float, "a float")


def env_optional_int(env: Mapping[str, str], key: str, default: int | None) -> int | None:
    """任意の整数環境変数を読む。

    Args:
        env: 環境変数マッピング。
        key: 変数名。
        default: 変数が無い場合に返すデフォルト値。

    Returns:
        パース済み整数値、``None``、またはデフォルト。
    """
    return _env_parse(env, key, default, int, "an integer")
