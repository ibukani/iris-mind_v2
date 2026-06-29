"""LLM プロバイダ診断のランタイム設定。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.parsing import env_bool, env_float, parse_bool, parse_float, parse_string
from iris.runtime.config.validation import require_greater_than_zero

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.runtime.config.parsing import TomlTable


class DiagnosticsMode(StrEnum):
    """LLM 起動時診断の動作モード。"""

    OFF = "off"
    WARN = "warn"
    STRICT = "strict"


_VALID_DIAGNOSTICS_MODES: frozenset[str] = frozenset({m.value for m in DiagnosticsMode})


@dataclass(frozen=True)
class RuntimeDiagnosticsConfig:
    """LLM プロバイダ診断のランタイム設定。

    mode の値に応じて ``run_startup_diagnostics`` の挙動が決まる:

    * ``off`` - 起動時診断を完全にスキップする。
    * ``warn`` - 診断を実施し、失敗を警告ログに残して起動を続行する。
    * ``strict`` - 診断を実施し、いずれかの readiness/warmup 結果が
      ``FAIL`` だった場合は ``ConfigError`` を送出して起動を中断する。

    ``warmup_models`` は provider 固有の warmup 動作を司る独立した
    フラグで、 ``off`` 以外のすべての mode で意味を持つ。
    """

    mode: DiagnosticsMode = DiagnosticsMode.WARN
    timeout_seconds: float = 5.0
    readiness_timeout_seconds: float = 5.0
    warmup_timeout_seconds: float = 120.0
    warmup_models: bool = False


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
    mode = config.mode
    if "mode" in table:
        mode = _validate_mode(parse_string(table["mode"], "diagnostics.mode"))

    timeout_seconds = config.timeout_seconds
    readiness_timeout_seconds = config.readiness_timeout_seconds
    warmup_timeout_seconds = config.warmup_timeout_seconds
    if "timeout_seconds" in table:
        timeout_seconds = parse_float(table["timeout_seconds"], "diagnostics.timeout_seconds")
        readiness_timeout_seconds = timeout_seconds
        warmup_timeout_seconds = timeout_seconds
    if "readiness_timeout_seconds" in table:
        readiness_timeout_seconds = parse_float(
            table["readiness_timeout_seconds"],
            "diagnostics.readiness_timeout_seconds",
        )
    if "warmup_timeout_seconds" in table:
        warmup_timeout_seconds = parse_float(
            table["warmup_timeout_seconds"],
            "diagnostics.warmup_timeout_seconds",
        )

    warmup_models = config.warmup_models
    if "warmup_models" in table:
        warmup_models = parse_bool(table["warmup_models"], "diagnostics.warmup_models")
    return _validate_config(
        RuntimeDiagnosticsConfig(
            mode=mode,
            timeout_seconds=timeout_seconds,
            readiness_timeout_seconds=readiness_timeout_seconds,
            warmup_timeout_seconds=warmup_timeout_seconds,
            warmup_models=warmup_models,
        ),
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
    raw_mode = env.get("IRIS_DIAGNOSTICS_MODE")
    mode = _validate_mode(raw_mode) if raw_mode is not None else config.mode
    timeout_seconds = config.timeout_seconds
    readiness_timeout_seconds = config.readiness_timeout_seconds
    warmup_timeout_seconds = config.warmup_timeout_seconds
    if "IRIS_DIAGNOSTICS_TIMEOUT_SECONDS" in env:
        timeout_seconds = env_float(env, "IRIS_DIAGNOSTICS_TIMEOUT_SECONDS", timeout_seconds)
        readiness_timeout_seconds = timeout_seconds
        warmup_timeout_seconds = timeout_seconds
    readiness_timeout_seconds = env_float(
        env,
        "IRIS_DIAGNOSTICS_READINESS_TIMEOUT_SECONDS",
        readiness_timeout_seconds,
    )
    warmup_timeout_seconds = env_float(
        env,
        "IRIS_DIAGNOSTICS_WARMUP_TIMEOUT_SECONDS",
        warmup_timeout_seconds,
    )
    return _validate_config(
        RuntimeDiagnosticsConfig(
            mode=mode,
            timeout_seconds=timeout_seconds,
            readiness_timeout_seconds=readiness_timeout_seconds,
            warmup_timeout_seconds=warmup_timeout_seconds,
            warmup_models=env_bool(
                env,
                "IRIS_DIAGNOSTICS_WARMUP_MODELS",
                default=config.warmup_models,
            ),
        ),
    )


def _validate_mode(value: str) -> DiagnosticsMode:
    """Diagnostics mode の値を検証する。

    Args:
        value: TOML / 環境変数から渡された mode 文字列。

    Returns:
        検証済みの mode。

    Raises:
        ConfigError: mode が ``off`` / ``warn`` / ``strict`` のいずれでもない場合。
    """
    for mode in DiagnosticsMode:
        if value == mode.value:
            return mode
    allowed = ", ".join(sorted(_VALID_DIAGNOSTICS_MODES))
    message = f"Invalid diagnostics.mode: {value}. Allowed values: {allowed}"
    raise ConfigError(message)


def _validate_config(config: RuntimeDiagnosticsConfig) -> RuntimeDiagnosticsConfig:
    """Diagnostics config の制約を検証する。

    Args:
        config: 検証対象の設定。

    Returns:
        検証済みの設定。
    """
    return replace(
        config,
        timeout_seconds=require_greater_than_zero(
            config.timeout_seconds,
            "diagnostics.timeout_seconds",
        ),
        readiness_timeout_seconds=require_greater_than_zero(
            config.readiness_timeout_seconds,
            "diagnostics.readiness_timeout_seconds",
        ),
        warmup_timeout_seconds=require_greater_than_zero(
            config.warmup_timeout_seconds,
            "diagnostics.warmup_timeout_seconds",
        ),
    )
