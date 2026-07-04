"""ランタイム安全性設定。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.parsing import (
    env_bool,
    env_optional_int,
    parse_bool,
    parse_int,
    parse_string,
)
from iris.runtime.config.validation import require_greater_than_zero

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.runtime.config.parsing import TomlTable


@dataclass(frozen=True)
class RuntimeSafetyConfig:
    """ランタイム安全性設定。

    mode が "development" の場合、出力安全性ゲートはパススルーになる。
    mode が "basic" または "strict" の場合、BasicOutputSafetyGate が使用される。
    strict は deterministic な proactive delivery policy も有効化する。
    high_risk_context_detection_enabled は、policy enforcement 前の typed safety context
    boundary と user-initiated safe response / redirect を明示的に有効化する。
    """

    mode: str = "development"
    max_output_chars: int = 4000
    high_risk_context_detection_enabled: bool = False


def apply_safety_toml(
    config: RuntimeSafetyConfig,
    table: TomlTable,
) -> RuntimeSafetyConfig:
    """TOML から safety 設定を適用する。

    Returns:
        検証済みのsafety設定。
    """
    mode = config.mode
    max_output_chars = config.max_output_chars
    high_risk_context_detection_enabled = config.high_risk_context_detection_enabled
    if "mode" in table:
        mode = _validate_mode(parse_string(table["mode"], "safety.mode"))
    if "max_output_chars" in table:
        max_output_chars = parse_int(
            table["max_output_chars"],
            "safety.max_output_chars",
        )
    if "high_risk_context_detection_enabled" in table:
        high_risk_context_detection_enabled = parse_bool(
            table["high_risk_context_detection_enabled"],
            "safety.high_risk_context_detection_enabled",
        )
    return _validate_config(
        RuntimeSafetyConfig(
            mode=mode,
            max_output_chars=max_output_chars,
            high_risk_context_detection_enabled=high_risk_context_detection_enabled,
        ),
    )


def apply_safety_env(
    config: RuntimeSafetyConfig,
    env: Mapping[str, str],
) -> RuntimeSafetyConfig:
    """環境変数から安全性設定を適用する。

    Args:
        config: ベースとなる安全性設定。
        env: 環境変数マッピング。

    Returns:
        環境変数値を反映した安全性設定。

    Raises:
        ConfigError: 環境変数値が不正な場合。
    """
    mode = config.mode
    if "IRIS_SAFETY_MODE" in env:
        mode = _validate_mode(env["IRIS_SAFETY_MODE"])
    max_output_chars = env_optional_int(
        env,
        "IRIS_SAFETY_MAX_OUTPUT_CHARS",
        config.max_output_chars,
    )
    if max_output_chars is None:
        message = "IRIS_SAFETY_MAX_OUTPUT_CHARS must be an integer"
        raise ConfigError(message)
    high_risk_context_detection_enabled = env_bool(
        env,
        "IRIS_SAFETY_HIGH_RISK_CONTEXT_DETECTION_ENABLED",
        default=config.high_risk_context_detection_enabled,
    )
    return _validate_config(
        RuntimeSafetyConfig(
            mode=mode,
            max_output_chars=max_output_chars,
            high_risk_context_detection_enabled=high_risk_context_detection_enabled,
        ),
    )


def _validate_mode(value: str) -> str:
    if value not in {"development", "basic", "strict"}:
        message = f"Invalid safety.mode: {value}. Allowed values: development, basic, strict"
        raise ConfigError(message)
    return value


def _validate_config(config: RuntimeSafetyConfig) -> RuntimeSafetyConfig:
    return replace(
        config,
        max_output_chars=require_greater_than_zero(
            config.max_output_chars,
            "safety.max_output_chars",
        ),
    )
