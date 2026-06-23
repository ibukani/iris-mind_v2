"""配送 outbox ランタイム設定。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import time

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.parsing import TomlTable, parse_bool, parse_float, parse_int, parse_string


@dataclass(frozen=True)
class RuntimeQuietHoursConfig:
    """配送 quiet hours 設定。"""

    enabled: bool = False
    start: str = "22:00"
    end: str = "08:00"
    timezone: str = "Asia/Tokyo"


@dataclass(frozen=True)
class RuntimeDeliveryConfig:
    """配送 outbox のランタイム設定。"""

    enabled: bool = True
    max_outbox_depth_per_provider: int = 100
    lease_seconds: float = 30.0
    max_attempts: int = 3
    retry_backoff_seconds: float = 30.0
    rate_limit_window_seconds: float = 1800.0
    quiet_hours: RuntimeQuietHoursConfig = RuntimeQuietHoursConfig()


def apply_delivery_toml(
    config: RuntimeDeliveryConfig,
    table: TomlTable,
) -> RuntimeDeliveryConfig:
    """配送設定に TOML テーブルのオーバーライドを適用する。

    Args:
        config: ベースとなる配送設定。
        table: ``[delivery]`` TOML テーブル。

    Returns:
        更新後の配送設定。
    """
    value = config
    if "enabled" in table:
        value = replace(value, enabled=parse_bool(table["enabled"], "delivery.enabled"))
    if "max_outbox_depth_per_provider" in table:
        value = replace(
            value,
            max_outbox_depth_per_provider=parse_int(
                table["max_outbox_depth_per_provider"],
                "delivery.max_outbox_depth_per_provider",
            ),
        )
    if "lease_seconds" in table:
        value = replace(
            value,
            lease_seconds=parse_float(table["lease_seconds"], "delivery.lease_seconds"),
        )
    if "max_attempts" in table:
        value = replace(
            value,
            max_attempts=parse_int(table["max_attempts"], "delivery.max_attempts"),
        )
    if "retry_backoff_seconds" in table:
        value = replace(
            value,
            retry_backoff_seconds=parse_float(
                table["retry_backoff_seconds"],
                "delivery.retry_backoff_seconds",
            ),
        )
    if "rate_limit_window_seconds" in table:
        value = replace(
            value,
            rate_limit_window_seconds=parse_float(
                table["rate_limit_window_seconds"],
                "delivery.rate_limit_window_seconds",
            ),
        )
    quiet_table = _quiet_hours_table(table)
    if quiet_table is not None:
        value = replace(
            value,
            quiet_hours=apply_quiet_hours_toml(value.quiet_hours, quiet_table),
        )
    return validate_delivery_config(value)


def apply_quiet_hours_toml(
    config: RuntimeQuietHoursConfig,
    table: TomlTable,
) -> RuntimeQuietHoursConfig:
    """静寂時間帯設定に TOML テーブルのオーバーライドを適用する。

    Args:
        config: ベースとなる quiet hours 設定。
        table: ``[delivery.quiet_hours]`` TOML テーブル。

    Returns:
        更新後の quiet hours 設定。
    """
    value = config
    if "enabled" in table:
        value = replace(value, enabled=parse_bool(table["enabled"], "delivery.quiet_hours.enabled"))
    if "start" in table:
        value = replace(value, start=parse_string(table["start"], "delivery.quiet_hours.start"))
    if "end" in table:
        value = replace(value, end=parse_string(table["end"], "delivery.quiet_hours.end"))
    if "timezone" in table:
        value = replace(
            value, timezone=parse_string(table["timezone"], "delivery.quiet_hours.timezone")
        )
    return value


def validate_delivery_config(config: RuntimeDeliveryConfig) -> RuntimeDeliveryConfig:
    """配送設定の数値範囲と quiet hours を検証する。

    Args:
        config: 検証対象の配送設定。

    Returns:
        RuntimeDeliveryConfig: 検証済み配送設定。

    Raises:
        ConfigError: 設定が制約に違反している場合。
    """
    if config.max_outbox_depth_per_provider <= 0:
        msg = "delivery.max_outbox_depth_per_provider must be > 0"
        raise ConfigError(msg)
    if config.lease_seconds <= 0:
        msg = "delivery.lease_seconds must be > 0"
        raise ConfigError(msg)
    if config.max_attempts <= 0:
        msg = "delivery.max_attempts must be > 0"
        raise ConfigError(msg)
    if config.retry_backoff_seconds < 0:
        msg = "delivery.retry_backoff_seconds must be >= 0"
        raise ConfigError(msg)
    if config.rate_limit_window_seconds < 0:
        msg = "delivery.rate_limit_window_seconds must be >= 0"
        raise ConfigError(msg)
    _parse_hhmm(config.quiet_hours.start, "delivery.quiet_hours.start")
    _parse_hhmm(config.quiet_hours.end, "delivery.quiet_hours.end")
    return config


def quiet_time(value: str, path: str) -> time:
    """検証済み HH:MM 文字列を time に変換する。

    Args:
        value: HH:MM 形式文字列。
        path: エラーメッセージに含める設定パス。

    Returns:
        time: 変換後の時刻。
    """
    return _parse_hhmm(value, path)


def _quiet_hours_table(table: TomlTable) -> TomlTable | None:
    """quiet_hours サブテーブルを取り出す。

    Args:
        table: ``[delivery]`` TOML テーブル。

    Returns:
        quiet_hours テーブル。キーがない場合は None。

    Raises:
        ConfigError: quiet_hours がテーブルでない場合。
    """
    if "quiet_hours" not in table:
        return None
    quiet_table = table["quiet_hours"]
    if not isinstance(quiet_table, dict):
        msg = "delivery.quiet_hours must be a table"
        raise ConfigError(msg)
    return quiet_table


_HHMM_PARTS = 2
_MAX_HOUR = 23
_MAX_MINUTE = 59


def _parse_hhmm(value: str, path: str) -> time:
    """HH:MM を解析し、不正なら ConfigError を送出する。

    Args:
        value: HH:MM 形式文字列。
        path: エラーメッセージに含める設定パス。

    Returns:
        time: 解析後の時刻。

    Raises:
        ConfigError: 形式が不正な場合。
    """
    parts = value.split(":")
    if len(parts) != _HHMM_PARTS:
        msg = f"{path} must be HH:MM"
        raise ConfigError(msg)
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as exc:
        msg = f"{path} must be HH:MM"
        raise ConfigError(msg) from exc
    if not 0 <= hour <= _MAX_HOUR or not 0 <= minute <= _MAX_MINUTE:
        msg = f"{path} must be HH:MM"
        raise ConfigError(msg)
    return time(hour=hour, minute=minute)
