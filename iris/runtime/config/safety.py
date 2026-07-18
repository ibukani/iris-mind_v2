"""ランタイム安全性設定。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.parsing import env_optional_int, parse_int, parse_string
from iris.runtime.config.validation import require_greater_than_zero

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.runtime.config.parsing import TomlTable


@dataclass(frozen=True)
class RuntimeSafetyConfig:
    """ランタイム安全性設定。

    mode が "development" の場合、すべての安全性ゲートはパススルーになる。
    mode が "basic" または "strict" の場合、BasicOutputSafetyGate が使用される。
    mode が "production" の場合、起動依存関係とdelivery surfaceをfail closedで検証する。
    strict / production は deterministic な proactive delivery policy も有効化する。
    """

    mode: str = "development"
    max_output_chars: int = 4000


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
    if "mode" in table:
        mode = _validate_mode(parse_string(table["mode"], "safety.mode"))
    if "max_output_chars" in table:
        max_output_chars = parse_int(
            table["max_output_chars"],
            "safety.max_output_chars",
        )
    return _validate_config(
        RuntimeSafetyConfig(mode=mode, max_output_chars=max_output_chars),
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
    return _validate_config(
        RuntimeSafetyConfig(mode=mode, max_output_chars=max_output_chars),
    )


def _validate_mode(value: str) -> str:
    if value not in {"development", "basic", "strict", "production"}:
        message = (
            f"Invalid safety.mode: {value}. Allowed values: development, basic, strict, production"
        )
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
