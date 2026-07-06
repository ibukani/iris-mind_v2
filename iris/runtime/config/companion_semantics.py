"""Companion semantics の runtime config。"""

from __future__ import annotations

from dataclasses import dataclass, replace

from iris.runtime.config.parsing import TomlTable, parse_bool


@dataclass(frozen=True)
class RuntimeCompanionSemanticsConfig:
    """Appraisal semantics 分離の初期有効化を制御する設定。"""

    appraisal_signals_enabled: bool = False
    dependency_risk_hint_enabled: bool = True
    persona_prompt_enabled: bool = False


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
    if "persona_prompt_enabled" in table:
        value = replace(
            value,
            persona_prompt_enabled=parse_bool(
                table["persona_prompt_enabled"],
                "companion_semantics.persona_prompt_enabled",
            ),
        )
    return validate_companion_semantics_config(value)


def validate_companion_semantics_config(
    config: RuntimeCompanionSemanticsConfig,
) -> RuntimeCompanionSemanticsConfig:
    """Companion semantics config の値を検証する。

    Returns:
        RuntimeCompanionSemanticsConfig: 検証済みの設定。
    """
    return config
