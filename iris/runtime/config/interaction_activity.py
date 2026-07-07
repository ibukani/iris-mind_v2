"""Interaction activity projectionのruntime config。"""

from __future__ import annotations

from dataclasses import dataclass, replace

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.parsing import TomlTable, parse_bool, parse_float


@dataclass(frozen=True)
class RuntimeInteractionActivityConfig:
    """Interaction projectionの有効化とserver-side TTL上限。"""

    enabled: bool = False
    max_ttl_seconds: float = 300.0


def apply_interaction_activity_toml(
    config: RuntimeInteractionActivityConfig,
    table: TomlTable,
) -> RuntimeInteractionActivityConfig:
    """`[interaction_activity]` TOML値を適用する。

    Returns:
        検証済みinteraction activity config。
    """
    value = config
    if "enabled" in table:
        value = replace(
            value,
            enabled=parse_bool(table["enabled"], "interaction_activity.enabled"),
        )
    if "max_ttl_seconds" in table:
        value = replace(
            value,
            max_ttl_seconds=parse_float(
                table["max_ttl_seconds"],
                "interaction_activity.max_ttl_seconds",
            ),
        )
    return validate_interaction_activity_config(value)


def validate_interaction_activity_config(
    config: RuntimeInteractionActivityConfig,
) -> RuntimeInteractionActivityConfig:
    """Interaction activity configを検証する。

    Returns:
        検証済みconfig。

    Raises:
        ConfigError: TTLが正でない場合。
    """
    if config.max_ttl_seconds <= 0:
        message = "interaction_activity.max_ttl_seconds must be greater than zero"
        raise ConfigError(message)
    return config
