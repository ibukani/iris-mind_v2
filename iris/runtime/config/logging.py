"""ランタイムロギング設定。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.parsing import parse_optional_string, parse_string

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.runtime.config.parsing import TomlTable


@dataclass(frozen=True)
class RuntimeLoggingConfig:
    """Loguru ベースのランタイム可観測性設定。"""

    level: str = "INFO"
    format: Literal["text", "json"] = "text"
    file_path: str | None = None
    rotation: str = "10 MB"
    retention: str = "7 days"


def validate_level(value: str) -> str:
    """ログレベル文字列を検証する。

    Returns:
        str: 正規化された検証済みログレベル。

    Raises:
        ConfigError: ログレベルが不正な場合。
    """
    allowed = {"TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    upper_value = value.upper()
    if upper_value not in allowed:
        msg = f"Invalid log level: {value}"
        raise ConfigError(msg)
    return upper_value


def validate_format(value: str) -> Literal["text", "json"]:
    """ログフォーマットを検証する。

    Returns:
        Literal["text", "json"]: 検証済みログフォーマット。

    Raises:
        ConfigError: ログフォーマットが不正な場合。
    """
    if value == "text":
        return "text"
    if value == "json":
        return "json"
    msg = f"Invalid log format: {value}"
    raise ConfigError(msg)


def apply_logging_toml(base: RuntimeLoggingConfig, table: TomlTable) -> RuntimeLoggingConfig:
    """TOML テーブルを RuntimeLoggingConfig に適用する。

    Returns:
        RuntimeLoggingConfig: オーバーライドを反映した新しいインスタンス。
    """
    level = (
        validate_level(parse_string(table["level"], "logging.level"))
        if "level" in table
        else base.level
    )
    format_val = (
        validate_format(parse_string(table["format"], "logging.format"))
        if "format" in table
        else base.format
    )
    file_path = (
        parse_optional_string(table["file_path"], "logging.file_path")
        if "file_path" in table
        else base.file_path
    )
    if not file_path:
        file_path = None
    rotation = (
        parse_string(table["rotation"], "logging.rotation")
        if "rotation" in table
        else base.rotation
    )
    retention = (
        parse_string(table["retention"], "logging.retention")
        if "retention" in table
        else base.retention
    )

    return replace(
        base,
        level=level,
        format=format_val,
        file_path=file_path,
        rotation=rotation,
        retention=retention,
    )


def apply_logging_env(base: RuntimeLoggingConfig, env: Mapping[str, str]) -> RuntimeLoggingConfig:
    """環境変数を RuntimeLoggingConfig に適用する。

    Returns:
        RuntimeLoggingConfig: 環境変数を反映した新しいインスタンス。
    """
    level = validate_level(env["IRIS_LOG_LEVEL"]) if "IRIS_LOG_LEVEL" in env else base.level
    format_val = (
        validate_format(env["IRIS_LOG_FORMAT"]) if "IRIS_LOG_FORMAT" in env else base.format
    )
    file_path = env.get("IRIS_LOG_FILE", base.file_path)

    return replace(
        base,
        level=level,
        format=format_val,
        file_path=file_path,
    )
