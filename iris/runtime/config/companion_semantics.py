"""Companion semantics の runtime config。"""

from __future__ import annotations

from dataclasses import dataclass, replace

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.parsing import TomlTable, parse_bool, parse_string


@dataclass(frozen=True)
class RuntimeCompanionSemanticsConfig:
    """Appraisal semantics 分離の初期有効化を制御する設定。"""

    appraisal_signals_enabled: bool = False
    dependency_risk_hint_enabled: bool = True
    global_persona_enabled: bool = False
    global_persona_path: str = "persona.toml"


def apply_companion_semantics_toml(
    config: RuntimeCompanionSemanticsConfig,
    table: TomlTable,
) -> RuntimeCompanionSemanticsConfig:
    """`[companion_semantics]` TOML 値を適用する。

    Returns:
        RuntimeCompanionSemanticsConfig: TOML を反映した設定。
    """
    value = config
    if "appraisal_signals_enabled" in table:
        value = replace(
            value,
            appraisal_signals_enabled=parse_bool(
                table["appraisal_signals_enabled"],
                "companion_semantics.appraisal_signals_enabled",
            ),
        )
    if "dependency_risk_hint_enabled" in table:
        value = replace(
            value,
            dependency_risk_hint_enabled=parse_bool(
                table["dependency_risk_hint_enabled"],
                "companion_semantics.dependency_risk_hint_enabled",
            ),
        )
    if "global_persona_enabled" in table:
        value = replace(
            value,
            global_persona_enabled=parse_bool(
                table["global_persona_enabled"],
                "companion_semantics.global_persona_enabled",
            ),
        )
    if "global_persona_path" in table:
        value = replace(
            value,
            global_persona_path=parse_string(
                table["global_persona_path"],
                "companion_semantics.global_persona_path",
            ),
        )
    return validate_companion_semantics_config(value)


def validate_companion_semantics_config(
    config: RuntimeCompanionSemanticsConfig,
) -> RuntimeCompanionSemanticsConfig:
    """Companion semantics config の値を検証する。

    Returns:
        RuntimeCompanionSemanticsConfig: 検証済みの設定。

    Raises:
        ConfigError: persona path が空の場合。
    """
    if not config.global_persona_path.strip():
        message = "companion_semantics.global_persona_path must be non-empty"
        raise ConfigError(message)
    return config
