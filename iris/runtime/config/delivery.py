"""配送 outbox ランタイム設定。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import time

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.parsing import TomlTable, parse_bool, parse_float, parse_int, parse_string
from iris.runtime.config.validation import require_greater_than_zero, require_zero_or_greater


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
    return _DeliveryConfigPatch.from_table(table).apply(config)


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
    return _apply_quiet_hours_patch(config, _QuietHoursPatch.from_table(table))


def validate_delivery_config(config: RuntimeDeliveryConfig) -> RuntimeDeliveryConfig:
    """配送設定の数値範囲と quiet hours を検証する。

    Args:
        config: 検証対象の配送設定。

    Returns:
        RuntimeDeliveryConfig: 検証済み配送設定。
    """
    return replace(
        config,
        max_outbox_depth_per_provider=require_greater_than_zero(
            config.max_outbox_depth_per_provider,
            "delivery.max_outbox_depth_per_provider",
        ),
        lease_seconds=require_greater_than_zero(
            config.lease_seconds,
            "delivery.lease_seconds",
        ),
        max_attempts=require_greater_than_zero(
            config.max_attempts,
            "delivery.max_attempts",
        ),
        retry_backoff_seconds=require_zero_or_greater(
            config.retry_backoff_seconds,
            "delivery.retry_backoff_seconds",
        ),
        rate_limit_window_seconds=require_zero_or_greater(
            config.rate_limit_window_seconds,
            "delivery.rate_limit_window_seconds",
        ),
        quiet_hours=_validate_quiet_hours(config.quiet_hours),
    )


def quiet_time(value: str, path: str) -> time:
    """検証済み HH:MM 文字列を time に変換する。

    Args:
        value: HH:MM 形式文字列。
        path: エラーメッセージに含める設定パス。

    Returns:
        time: 変換後の時刻。
    """
    return _parse_hhmm(value, path)


def _quiet_hours_patch(table: TomlTable) -> _QuietHoursPatch | None:
    """quiet_hours サブテーブルを patch へ変換する。

    Args:
        table: ``[delivery]`` TOML テーブル。

    Returns:
        quiet_hours patch。キーがない場合は None。

    Raises:
        ConfigError: quiet_hours がテーブルでない場合。
    """
    if "quiet_hours" not in table:
        return None
    quiet_table = table["quiet_hours"]
    if not isinstance(quiet_table, dict):
        msg = "delivery.quiet_hours must be a table"
        raise ConfigError(msg)
    return _QuietHoursPatch.from_table(quiet_table)


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
    """
    parts = value.split(":")
    if len(parts) != _HHMM_PARTS:
        _raise_invalid_hhmm(path)
    hour = 0
    minute = 0
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as exc:
        _raise_invalid_hhmm(path, exc)
    if not 0 <= hour <= _MAX_HOUR or not 0 <= minute <= _MAX_MINUTE:
        _raise_invalid_hhmm(path)
    return time(hour=hour, minute=minute)


def _validate_quiet_hours(config: RuntimeQuietHoursConfig) -> RuntimeQuietHoursConfig:
    """Quiet hours の開始・終了時刻を検証する。

    Args:
        config: 検証対象の quiet hours 設定。

    Returns:
        検証済みの quiet hours 設定。
    """
    _parse_hhmm(config.start, "delivery.quiet_hours.start")
    _parse_hhmm(config.end, "delivery.quiet_hours.end")
    return config


def _raise_invalid_hhmm(path: str, exc: ValueError | None = None) -> None:
    """HH:MM 形式の不正を共通表現で送出する。

    Raises:
        ConfigError: 形式が不正な場合。
    """
    msg = f"{path} must be HH:MM"
    if exc is None:
        raise ConfigError(msg)
    raise ConfigError(msg) from exc


@dataclass(frozen=True)
class _QuietHoursPatch:
    """quiet hours の optional 更新値を束ねる。"""

    enabled: bool | None = None
    start: str | None = None
    end: str | None = None
    timezone: str | None = None

    @classmethod
    def from_table(cls, table: TomlTable) -> _QuietHoursPatch:
        """TOML テーブルから patch を組み立てる。

        Returns:
            組み立てた quiet hours patch。
        """
        return cls(
            enabled=parse_bool(table["enabled"], "delivery.quiet_hours.enabled")
            if "enabled" in table
            else None,
            start=parse_string(table["start"], "delivery.quiet_hours.start")
            if "start" in table
            else None,
            end=parse_string(table["end"], "delivery.quiet_hours.end") if "end" in table else None,
            timezone=parse_string(table["timezone"], "delivery.quiet_hours.timezone")
            if "timezone" in table
            else None,
        )

    def apply(self, config: RuntimeQuietHoursConfig) -> RuntimeQuietHoursConfig:
        """Quiet hours 設定へ patch を適用する。

        Returns:
            更新後の quiet hours 設定。
        """
        value = config
        if self.enabled is not None:
            value = replace(value, enabled=self.enabled)
        if self.start is not None:
            value = replace(value, start=self.start)
        if self.end is not None:
            value = replace(value, end=self.end)
        if self.timezone is not None:
            value = replace(value, timezone=self.timezone)
        return value


@dataclass(frozen=True)
class _DeliveryConfigPatch:
    """delivery の optional 更新値を束ねる。"""

    enabled: bool | None = None
    max_outbox_depth_per_provider: int | None = None
    lease_seconds: float | None = None
    max_attempts: int | None = None
    retry_backoff_seconds: float | None = None
    rate_limit_window_seconds: float | None = None
    quiet_hours: _QuietHoursPatch | None = None

    @classmethod
    def from_table(cls, table: TomlTable) -> _DeliveryConfigPatch:
        """TOML テーブルから delivery patch を組み立てる。

        Returns:
            組み立てた delivery patch。
        """
        return cls(
            enabled=(
                parse_bool(table["enabled"], "delivery.enabled") if "enabled" in table else None
            ),
            max_outbox_depth_per_provider=(
                parse_int(
                    table["max_outbox_depth_per_provider"],
                    "delivery.max_outbox_depth_per_provider",
                )
                if "max_outbox_depth_per_provider" in table
                else None
            ),
            lease_seconds=(
                parse_float(table["lease_seconds"], "delivery.lease_seconds")
                if "lease_seconds" in table
                else None
            ),
            max_attempts=(
                parse_int(table["max_attempts"], "delivery.max_attempts")
                if "max_attempts" in table
                else None
            ),
            retry_backoff_seconds=(
                parse_float(
                    table["retry_backoff_seconds"],
                    "delivery.retry_backoff_seconds",
                )
                if "retry_backoff_seconds" in table
                else None
            ),
            rate_limit_window_seconds=(
                parse_float(
                    table["rate_limit_window_seconds"],
                    "delivery.rate_limit_window_seconds",
                )
                if "rate_limit_window_seconds" in table
                else None
            ),
            quiet_hours=_quiet_hours_patch(table),
        )

    def apply(self, config: RuntimeDeliveryConfig) -> RuntimeDeliveryConfig:
        """Delivery 設定へ patch を適用して検証する。

        Returns:
            検証済みの delivery 設定。
        """
        value = config
        if self.enabled is not None:
            value = replace(value, enabled=self.enabled)
        if self.max_outbox_depth_per_provider is not None:
            value = replace(
                value,
                max_outbox_depth_per_provider=self.max_outbox_depth_per_provider,
            )
        if self.lease_seconds is not None:
            value = replace(value, lease_seconds=self.lease_seconds)
        if self.max_attempts is not None:
            value = replace(value, max_attempts=self.max_attempts)
        if self.retry_backoff_seconds is not None:
            value = replace(value, retry_backoff_seconds=self.retry_backoff_seconds)
        if self.rate_limit_window_seconds is not None:
            value = replace(value, rate_limit_window_seconds=self.rate_limit_window_seconds)
        if self.quiet_hours is not None:
            value = replace(value, quiet_hours=self.quiet_hours.apply(value.quiet_hours))
        return validate_delivery_config(value)


def _apply_quiet_hours_patch(
    config: RuntimeQuietHoursConfig,
    patch: _QuietHoursPatch | None,
) -> RuntimeQuietHoursConfig:
    """Quiet hours patch を適用する。

    Args:
        config: ベースとなる quiet hours 設定。
        patch: 更新値。None なら変更なし。

    Returns:
        更新後の quiet hours 設定。
    """
    if patch is None:
        return config
    return patch.apply(config)
