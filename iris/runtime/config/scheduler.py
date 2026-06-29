"""スケジューラーランタイム設定。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

from iris.runtime.config.parsing import (
    TomlTable,
    env_optional_float,
    parse_bool,
    parse_float,
    parse_int,
)
from iris.runtime.config.validation import require_greater_than_zero, require_zero_or_greater


@dataclass(frozen=True)
class RuntimeSchedulerConfig:
    """スケジューラーループと idle tick のランタイム設定。"""

    enabled: bool = False
    interval_seconds: float = 30.0
    idle_threshold_seconds: float = 600.0
    min_interval_per_target_seconds: float = 1800.0
    target_stale_after_seconds: float = 604800.0
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
            interval_seconds=parse_float(
                table["interval_seconds"],
                "scheduler.interval_seconds",
            ),
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
    if "target_stale_after_seconds" in table:
        value = replace(
            value,
            target_stale_after_seconds=parse_float(
                table["target_stale_after_seconds"],
                "scheduler.target_stale_after_seconds",
            ),
        )
    if "max_due_per_run" in table:
        value = replace(
            value,
            max_due_per_run=parse_int(
                table["max_due_per_run"],
                "scheduler.max_due_per_run",
            ),
        )
    return validate_scheduler_config(value)


def apply_scheduler_env(
    config: RuntimeSchedulerConfig,
    env: Mapping[str, str],
) -> RuntimeSchedulerConfig:
    """環境変数オーバーライドをスケジューラー設定に適用する。

    Args:
        config: ベースとなるスケジューラー設定。
        env: 環境変数のマッピング。

    Returns:
        更新後のスケジューラー設定。
    """
    target_stale_after_seconds = env_optional_float(
        env,
        "IRIS_SCHEDULER_TARGET_STALE_AFTER_SECONDS",
        None,
    )
    if target_stale_after_seconds is None:
        return validate_scheduler_config(config)
    return validate_scheduler_config(
        replace(
            config,
            target_stale_after_seconds=target_stale_after_seconds,
        ),
    )


def validate_scheduler_config(config: RuntimeSchedulerConfig) -> RuntimeSchedulerConfig:
    """スケジューラー設定の数値範囲を検証する。

    Args:
        config: 検証対象のスケジューラー設定。

    Returns:
        RuntimeSchedulerConfig: 検証済みスケジューラー設定。
    """
    return replace(
        config,
        interval_seconds=require_greater_than_zero(
            config.interval_seconds,
            "scheduler.interval_seconds",
        ),
        idle_threshold_seconds=require_zero_or_greater(
            config.idle_threshold_seconds,
            "scheduler.idle_threshold_seconds",
        ),
        min_interval_per_target_seconds=require_zero_or_greater(
            config.min_interval_per_target_seconds,
            "scheduler.min_interval_per_target_seconds",
        ),
        target_stale_after_seconds=require_greater_than_zero(
            config.target_stale_after_seconds,
            "scheduler.target_stale_after_seconds",
        ),
        max_due_per_run=require_greater_than_zero(
            config.max_due_per_run,
            "scheduler.max_due_per_run",
        ),
    )
