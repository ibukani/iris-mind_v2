"""LLM プロバイダ診断のランタイム設定。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.parsing import (
    env_bool,
    env_float,
    parse_bool,
    parse_float,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.runtime.config.parsing import TomlTable


@dataclass(frozen=True)
class RuntimeDiagnosticsConfig:
    """LLM プロバイダ診断のランタイム設定。

    サーバー起動時に各モデルスロットへ診断チェックを実行するかを制御する。
    fake プロバイダのスロットは診断対象から自動的に除外される。
    """

    enabled: bool = True
    timeout_seconds: float = 5.0
    fail_fast: bool = False
    warmup_models: bool = False
    log_issues_as_warnings: bool = True


def apply_diagnostics_toml(
    config: RuntimeDiagnosticsConfig,
    table: TomlTable,
) -> RuntimeDiagnosticsConfig:
    """TOML ``[diagnostics]`` セクションを diagnostics config に適用する。

    Args:
        config: ベースとなる diagnostics config。
        table: 解析済み TOML ``[diagnostics]`` テーブル。

    Returns:
        TOML 値を反映した diagnostics config。
    """
    enabled = config.enabled
    if "enabled" in table:
        enabled = parse_bool(table["enabled"], "diagnostics.enabled")

    timeout_seconds = config.timeout_seconds
    if "timeout_seconds" in table:
        timeout_seconds = parse_float(
            table["timeout_seconds"],
            "diagnostics.timeout_seconds",
        )

    fail_fast = config.fail_fast
    if "fail_fast" in table:
        fail_fast = parse_bool(table["fail_fast"], "diagnostics.fail_fast")

    warmup_models = config.warmup_models
    if "warmup_models" in table:
        warmup_models = parse_bool(
            table["warmup_models"],
            "diagnostics.warmup_models",
        )

    log_issues_as_warnings = config.log_issues_as_warnings
    if "log_issues_as_warnings" in table:
        log_issues_as_warnings = parse_bool(
            table["log_issues_as_warnings"],
            "diagnostics.log_issues_as_warnings",
        )

    return _validate_config(
        RuntimeDiagnosticsConfig(
            enabled=enabled,
            timeout_seconds=timeout_seconds,
            fail_fast=fail_fast,
            warmup_models=warmup_models,
            log_issues_as_warnings=log_issues_as_warnings,
        )
    )


def apply_diagnostics_env(
    config: RuntimeDiagnosticsConfig,
    env: Mapping[str, str],
) -> RuntimeDiagnosticsConfig:
    """環境変数オーバーライドを diagnostics config へ適用する。

    Args:
        config: ベースとなる diagnostics config。
        env: 環境変数マッピング。

    Returns:
        環境変数値を反映した diagnostics config。
    """
    return _validate_config(
        RuntimeDiagnosticsConfig(
            enabled=env_bool(env, "IRIS_DIAGNOSTICS_ENABLED", default=config.enabled),
            timeout_seconds=env_float(
                env,
                "IRIS_DIAGNOSTICS_TIMEOUT_SECONDS",
                config.timeout_seconds,
            ),
            fail_fast=env_bool(env, "IRIS_DIAGNOSTICS_FAIL_FAST", default=config.fail_fast),
            warmup_models=env_bool(
                env,
                "IRIS_DIAGNOSTICS_WARMUP_MODELS",
                default=config.warmup_models,
            ),
            log_issues_as_warnings=env_bool(
                env,
                "IRIS_DIAGNOSTICS_LOG_ISSUES_AS_WARNINGS",
                default=config.log_issues_as_warnings,
            ),
        )
    )


def _validate_config(config: RuntimeDiagnosticsConfig) -> RuntimeDiagnosticsConfig:
    """Diagnostics config の制約を検証する。

    Args:
        config: 検証対象の設定。

    Returns:
        検証済みの設定。

    Raises:
        ConfigError: タイムアウトが正の値でない場合。
    """
    if config.timeout_seconds <= 0:
        message = "diagnostics.timeout_seconds must be greater than zero"
        raise ConfigError(message)
    return replace(config)
