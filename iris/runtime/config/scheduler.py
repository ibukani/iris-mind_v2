"""スケジューラーランタイム設定。"""

from __future__ import annotations

from dataclasses import dataclass, replace

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.parsing import TomlTable, parse_bool, parse_float, parse_int


@dataclass(frozen=True)
class RuntimeSchedulerConfig:
    """スケジューラーループと idle tick のランタイム設定。"""

    enabled: bool = False
    interval_seconds: float = 30.0
    idle_threshold_seconds: float = 600.0
    min_interval_per_target_seconds: float = 1800.0
    max_due_per_run: int = 10


def apply_scheduler_toml(
    config: RuntimeSchedulerConfig,
    table: TomlTable,
) -> RuntimeSchedulerConfig:
    """スケジューラー設定に TOML テーブルのオーバーライドを適用する。

    Args:
        config: ベースとなるスケジューラー設定。
        table: ``[scheduler]`` TOML テーブル。

    Returns:
        更新後のスケジューラー設定。
    """
    value = config
    if "enabled" in table:
        value = replace(value, enabled=parse_bool(table["enabled"], "scheduler.enabled"))
    if "interval_seconds" in table:
        value = replace(
            value,
            interval_seconds=parse_float(table["interval_seconds"], "scheduler.interval_seconds"),
        )
    if "idle_threshold_seconds" in table:
        value = replace(
            value,
            idle_threshold_seconds=parse_float(
                table["idle_threshold_seconds"],
                "scheduler.idle_threshold_seconds",
            ),
        )
    if "min_interval_per_target_seconds" in table:
        value = replace(
            value,
            min_interval_per_target_seconds=parse_float(
                table["min_interval_per_target_seconds"],
                "scheduler.min_interval_per_target_seconds",
            ),
        )
    if "max_due_per_run" in table:
        value = replace(
            value,
            max_due_per_run=parse_int(table["max_due_per_run"], "scheduler.max_due_per_run"),
        )
    return validate_scheduler_config(value)


def validate_scheduler_config(config: RuntimeSchedulerConfig) -> RuntimeSchedulerConfig:
    """スケジューラー設定の数値範囲を検証する。

    Args:
        config: 検証対象のスケジューラー設定。

    Returns:
        RuntimeSchedulerConfig: 検証済みスケジューラー設定。

    Raises:
        ConfigError: 設定が制約に違反している場合。
    """
    if config.interval_seconds <= 0:
        msg = "scheduler.interval_seconds must be > 0"
        raise ConfigError(msg)
    if config.idle_threshold_seconds < 0:
        msg = "scheduler.idle_threshold_seconds must be >= 0"
        raise ConfigError(msg)
    if config.min_interval_per_target_seconds < 0:
        msg = "scheduler.min_interval_per_target_seconds must be >= 0"
        raise ConfigError(msg)
    if config.max_due_per_run <= 0:
        msg = "scheduler.max_due_per_run must be > 0"
        raise ConfigError(msg)
    return config
