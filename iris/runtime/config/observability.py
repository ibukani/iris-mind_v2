"""Runtime observability latency budget configuration."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from iris.runtime.config.parsing import parse_bool, parse_float, table_or_empty
from iris.runtime.config.validation import require_greater_than_zero
from iris.runtime.observability.ports import RuntimeLatencyBudget

if TYPE_CHECKING:
    from iris.runtime.config.parsing import TomlTable


@dataclass(frozen=True)
class RuntimeObservabilityConfig:
    """Runtime 可観測性設定。"""

    latency_budget: RuntimeLatencyBudget = field(default_factory=RuntimeLatencyBudget)


def apply_observability_toml(
    config: RuntimeObservabilityConfig,
    table: TomlTable,
) -> RuntimeObservabilityConfig:
    """TOML ``[observability]`` セクションを observability config に適用する。

    Args:
        config: ベースとなる observability config。
        table: 解析済み TOML ``[observability]`` テーブル。

    Returns:
        TOML 値を反映した observability config。
    """
    return replace(
        config,
        latency_budget=apply_latency_budget_toml(
            config.latency_budget,
            table_or_empty(table, "latency_budget", path="observability.latency_budget"),
        ),
    )


def apply_latency_budget_toml(
    budget: RuntimeLatencyBudget,
    table: TomlTable,
) -> RuntimeLatencyBudget:
    """TOML ``[observability.latency_budget]`` を latency budget に適用する。

    Args:
        budget: ベースとなる latency budget。
        table: 解析済み TOML section。

    Returns:
        TOML 値を反映した latency budget。
    """
    updated = RuntimeLatencyBudget(
        enabled=_bool_or_default(table, "enabled", default=budget.enabled),
        slow_warning_enabled=_bool_or_default(
            table,
            "slow_warning_enabled",
            default=budget.slow_warning_enabled,
        ),
        handle_observation_ms=_float_or_default(
            table,
            "handle_observation_ms",
            budget.handle_observation_ms,
        ),
        observation_integration_ms=_float_or_default(
            table,
            "observation_integration_ms",
            budget.observation_integration_ms,
        ),
        workspace_context_assembly_ms=_float_or_default(
            table,
            "workspace_context_assembly_ms",
            budget.workspace_context_assembly_ms,
        ),
        conversation_context_load_ms=_float_or_default(
            table,
            "conversation_context_load_ms",
            budget.conversation_context_load_ms,
        ),
        cognitive_processing_ms=_float_or_default(
            table,
            "cognitive_processing_ms",
            budget.cognitive_processing_ms,
        ),
        llm_generate_ms=_float_or_default(table, "llm_generate_ms", budget.llm_generate_ms),
        conversation_record_ms=_float_or_default(
            table,
            "conversation_record_ms",
            budget.conversation_record_ms,
        ),
        transcript_append_ms=_float_or_default(
            table,
            "transcript_append_ms",
            budget.transcript_append_ms,
        ),
        runtime_learning_hook_ms=_float_or_default(
            table,
            "runtime_learning_hook_ms",
            budget.runtime_learning_hook_ms,
        ),
        background_enqueue_ms=_float_or_default(
            table,
            "background_enqueue_ms",
            budget.background_enqueue_ms,
        ),
        classifier_call_ms=_float_or_default(
            table, "classifier_call_ms", budget.classifier_call_ms
        ),
        embedding_call_ms=_float_or_default(table, "embedding_call_ms", budget.embedding_call_ms),
        reranker_call_ms=_float_or_default(table, "reranker_call_ms", budget.reranker_call_ms),
    )
    return validate_latency_budget(updated)


def validate_observability_config(
    config: RuntimeObservabilityConfig,
) -> RuntimeObservabilityConfig:
    """Observability config の制約を検証する。

    Args:
        config: 検証対象の設定。

    Returns:
        検証済みの設定。
    """
    return replace(config, latency_budget=validate_latency_budget(config.latency_budget))


def validate_latency_budget(budget: RuntimeLatencyBudget) -> RuntimeLatencyBudget:
    """Latency budget の全数値が正であることを検証する。

    Args:
        budget: 検証対象の latency budget。

    Returns:
        検証済みの latency budget。
    """
    return RuntimeLatencyBudget(
        enabled=budget.enabled,
        slow_warning_enabled=budget.slow_warning_enabled,
        handle_observation_ms=require_greater_than_zero(
            budget.handle_observation_ms,
            "observability.latency_budget.handle_observation_ms",
        ),
        observation_integration_ms=require_greater_than_zero(
            budget.observation_integration_ms,
            "observability.latency_budget.observation_integration_ms",
        ),
        workspace_context_assembly_ms=require_greater_than_zero(
            budget.workspace_context_assembly_ms,
            "observability.latency_budget.workspace_context_assembly_ms",
        ),
        conversation_context_load_ms=require_greater_than_zero(
            budget.conversation_context_load_ms,
            "observability.latency_budget.conversation_context_load_ms",
        ),
        cognitive_processing_ms=require_greater_than_zero(
            budget.cognitive_processing_ms,
            "observability.latency_budget.cognitive_processing_ms",
        ),
        llm_generate_ms=require_greater_than_zero(
            budget.llm_generate_ms,
            "observability.latency_budget.llm_generate_ms",
        ),
        conversation_record_ms=require_greater_than_zero(
            budget.conversation_record_ms,
            "observability.latency_budget.conversation_record_ms",
        ),
        transcript_append_ms=require_greater_than_zero(
            budget.transcript_append_ms,
            "observability.latency_budget.transcript_append_ms",
        ),
        runtime_learning_hook_ms=require_greater_than_zero(
            budget.runtime_learning_hook_ms,
            "observability.latency_budget.runtime_learning_hook_ms",
        ),
        background_enqueue_ms=require_greater_than_zero(
            budget.background_enqueue_ms,
            "observability.latency_budget.background_enqueue_ms",
        ),
        classifier_call_ms=require_greater_than_zero(
            budget.classifier_call_ms,
            "observability.latency_budget.classifier_call_ms",
        ),
        embedding_call_ms=require_greater_than_zero(
            budget.embedding_call_ms,
            "observability.latency_budget.embedding_call_ms",
        ),
        reranker_call_ms=require_greater_than_zero(
            budget.reranker_call_ms,
            "observability.latency_budget.reranker_call_ms",
        ),
    )


def _float_or_default(table: TomlTable, key: str, default: float) -> float:
    value = table.get(key)
    if value is None:
        return default
    return parse_float(value, f"observability.latency_budget.{key}")


def _bool_or_default(table: TomlTable, key: str, *, default: bool) -> bool:
    value = table.get(key)
    if value is None:
        return default
    return parse_bool(value, f"observability.latency_budget.{key}")
