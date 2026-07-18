"""Runtime source retrieval の設定。"""

from __future__ import annotations

from dataclasses import dataclass, replace

from iris.runtime.config.parsing import TomlTable, parse_bool, parse_int
from iris.runtime.config.validation import require_zero_or_greater


@dataclass(frozen=True)
class RuntimeRetrievalConfig:
    """Project / transcript prompt retrieval の default-off 設定。"""

    enabled: bool = False
    max_total_items: int = 12


def apply_retrieval_toml(
    config: RuntimeRetrievalConfig,
    table: TomlTable,
) -> RuntimeRetrievalConfig:
    """`[retrieval]` TOML 値を適用する。

    Returns:
        更新済みの retrieval 設定。
    """
    value = config
    if "enabled" in table:
        value = replace(value, enabled=parse_bool(table["enabled"], "retrieval.enabled"))
    if "max_total_items" in table:
        value = replace(
            value,
            max_total_items=parse_int(table["max_total_items"], "retrieval.max_total_items"),
        )
    return validate_retrieval_config(value)


def validate_retrieval_config(config: RuntimeRetrievalConfig) -> RuntimeRetrievalConfig:
    """Retrieval の item budget を検証する。

    Returns:
        検証済みの retrieval 設定。
    """
    return replace(
        config,
        max_total_items=require_zero_or_greater(
            config.max_total_items,
            "retrieval.max_total_items",
        ),
    )
