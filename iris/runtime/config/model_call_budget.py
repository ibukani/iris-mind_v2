"""モデル呼び出し予算と cascade policy のランタイム設定。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from iris.contracts.model_policy import CascadeFallbackBehavior, ModelCallSite
from iris.runtime.config.errors import ConfigError
from iris.runtime.config.parsing import (
    parse_bool,
    parse_float,
    parse_int,
    parse_string,
    table_or_empty,
)

if TYPE_CHECKING:
    from iris.runtime.config.parsing import TomlTable, TomlValue


@dataclass(frozen=True)
class RuntimeFeatureModelCallBudget:
    """1つの feature / hot path に対するモデル呼び出し予算。"""

    large_llm_max_calls: int = 0
    small_classifier_max_calls: int = 0
    embedding_max_calls: int = 0
    reranker_max_calls: int = 0
    background_llm_max_calls: int = 0
    confidence_threshold: float = 0.65
    low_confidence_fallback: CascadeFallbackBehavior = CascadeFallbackBehavior.NO_OP
    high_risk_escalation_allowed: bool = False
    uncertain_escalation_allowed: bool = False
    enqueue_only: bool = False


@dataclass(frozen=True)
class RuntimeModelCallBudgetConfig:
    """Runtime 全体の feature 別モデル呼び出し予算。"""

    enabled: bool = True
    user_response_hot_path: RuntimeFeatureModelCallBudget = RuntimeFeatureModelCallBudget(
        large_llm_max_calls=1,
        small_classifier_max_calls=1,
        embedding_max_calls=1,
        reranker_max_calls=1,
        low_confidence_fallback=CascadeFallbackBehavior.DETERMINISTIC_BASELINE,
        high_risk_escalation_allowed=True,
        uncertain_escalation_allowed=True,
    )
    proactive: RuntimeFeatureModelCallBudget = RuntimeFeatureModelCallBudget(
        large_llm_max_calls=1,
        small_classifier_max_calls=1,
        embedding_max_calls=1,
        background_llm_max_calls=1,
        low_confidence_fallback=CascadeFallbackBehavior.DEFER,
        high_risk_escalation_allowed=True,
        uncertain_escalation_allowed=True,
    )
    memory_extraction: RuntimeFeatureModelCallBudget = RuntimeFeatureModelCallBudget(
        small_classifier_max_calls=1,
        embedding_max_calls=1,
        background_llm_max_calls=1,
        low_confidence_fallback=CascadeFallbackBehavior.ENQUEUE_BACKGROUND,
    )
    reflection: RuntimeFeatureModelCallBudget = RuntimeFeatureModelCallBudget(
        embedding_max_calls=1,
        background_llm_max_calls=1,
        low_confidence_fallback=CascadeFallbackBehavior.DEFER,
    )
    relationship_update: RuntimeFeatureModelCallBudget = RuntimeFeatureModelCallBudget(
        small_classifier_max_calls=1,
        embedding_max_calls=1,
        background_llm_max_calls=1,
        low_confidence_fallback=CascadeFallbackBehavior.NO_OP,
    )
    interaction_policy_candidate: RuntimeFeatureModelCallBudget = RuntimeFeatureModelCallBudget(
        small_classifier_max_calls=1,
        embedding_max_calls=1,
        reranker_max_calls=1,
        background_llm_max_calls=1,
        low_confidence_fallback=CascadeFallbackBehavior.REJECT,
    )
    runtime_learning_hook: RuntimeFeatureModelCallBudget = RuntimeFeatureModelCallBudget(
        background_llm_max_calls=1,
        low_confidence_fallback=CascadeFallbackBehavior.ENQUEUE_BACKGROUND,
        enqueue_only=True,
    )


def default_model_call_budget_config() -> RuntimeModelCallBudgetConfig:
    """既定のモデル呼び出し予算を返す。

    Returns:
        RuntimeModelCallBudgetConfig: 既定設定。
    """
    return RuntimeModelCallBudgetConfig()


def apply_model_call_budget_toml(
    config: RuntimeModelCallBudgetConfig,
    table: TomlTable,
) -> RuntimeModelCallBudgetConfig:
    """TOML ``[model_call_budget]`` セクションを適用する。

    Returns:
        RuntimeModelCallBudgetConfig: TOML を反映して検証済みの設定。
    """
    value = config
    if "enabled" in table:
        value = replace(value, enabled=parse_bool(table["enabled"], "model_call_budget.enabled"))
    value = replace(
        value,
        user_response_hot_path=_apply_feature_budget_toml(
            value.user_response_hot_path,
            table,
            ModelCallSite.USER_RESPONSE_HOT_PATH,
        ),
        proactive=_apply_feature_budget_toml(value.proactive, table, ModelCallSite.PROACTIVE),
        memory_extraction=_apply_feature_budget_toml(
            value.memory_extraction,
            table,
            ModelCallSite.MEMORY_EXTRACTION,
        ),
        reflection=_apply_feature_budget_toml(value.reflection, table, ModelCallSite.REFLECTION),
        relationship_update=_apply_feature_budget_toml(
            value.relationship_update,
            table,
            ModelCallSite.RELATIONSHIP_UPDATE,
        ),
        interaction_policy_candidate=_apply_feature_budget_toml(
            value.interaction_policy_candidate,
            table,
            ModelCallSite.INTERACTION_POLICY_CANDIDATE,
        ),
        runtime_learning_hook=_apply_feature_budget_toml(
            value.runtime_learning_hook,
            table,
            ModelCallSite.RUNTIME_LEARNING_HOOK,
        ),
    )
    return validate_model_call_budget_config(value)


def validate_model_call_budget_config(
    config: RuntimeModelCallBudgetConfig,
) -> RuntimeModelCallBudgetConfig:
    """モデル呼び出し予算の範囲と hot-path 不変条件を検証する。

    Returns:
        RuntimeModelCallBudgetConfig: 各 feature budget を正規化した設定。
    """
    return replace(
        config,
        user_response_hot_path=_validate_feature_budget(
            config.user_response_hot_path,
            ModelCallSite.USER_RESPONSE_HOT_PATH,
        ),
        proactive=_validate_feature_budget(config.proactive, ModelCallSite.PROACTIVE),
        memory_extraction=_validate_feature_budget(
            config.memory_extraction,
            ModelCallSite.MEMORY_EXTRACTION,
        ),
        reflection=_validate_feature_budget(config.reflection, ModelCallSite.REFLECTION),
        relationship_update=_validate_feature_budget(
            config.relationship_update,
            ModelCallSite.RELATIONSHIP_UPDATE,
        ),
        interaction_policy_candidate=_validate_feature_budget(
            config.interaction_policy_candidate,
            ModelCallSite.INTERACTION_POLICY_CANDIDATE,
        ),
        runtime_learning_hook=_validate_feature_budget(
            config.runtime_learning_hook,
            ModelCallSite.RUNTIME_LEARNING_HOOK,
        ),
    )


def feature_budget_for_site(
    config: RuntimeModelCallBudgetConfig,
    site: ModelCallSite,
) -> RuntimeFeatureModelCallBudget:
    """Call site に対応する feature budget を返す。

    Returns:
        RuntimeFeatureModelCallBudget: call site に対応する budget。
    """
    budgets = {
        ModelCallSite.USER_RESPONSE_HOT_PATH: config.user_response_hot_path,
        ModelCallSite.PROACTIVE: config.proactive,
        ModelCallSite.MEMORY_EXTRACTION: config.memory_extraction,
        ModelCallSite.REFLECTION: config.reflection,
        ModelCallSite.RELATIONSHIP_UPDATE: config.relationship_update,
        ModelCallSite.INTERACTION_POLICY_CANDIDATE: config.interaction_policy_candidate,
        ModelCallSite.RUNTIME_LEARNING_HOOK: config.runtime_learning_hook,
    }
    return budgets[site]


def _apply_feature_budget_toml(
    budget: RuntimeFeatureModelCallBudget,
    root_table: TomlTable,
    site: ModelCallSite,
) -> RuntimeFeatureModelCallBudget:
    path = f"model_call_budget.{site.value}"
    table = table_or_empty(root_table, site.value, path=path)
    return replace(
        budget,
        large_llm_max_calls=_optional_int(
            table,
            "large_llm_max_calls",
            path,
            budget.large_llm_max_calls,
        ),
        small_classifier_max_calls=_optional_int(
            table,
            "small_classifier_max_calls",
            path,
            budget.small_classifier_max_calls,
        ),
        embedding_max_calls=_optional_int(
            table,
            "embedding_max_calls",
            path,
            budget.embedding_max_calls,
        ),
        reranker_max_calls=_optional_int(
            table,
            "reranker_max_calls",
            path,
            budget.reranker_max_calls,
        ),
        background_llm_max_calls=_optional_int(
            table,
            "background_llm_max_calls",
            path,
            budget.background_llm_max_calls,
        ),
        confidence_threshold=_optional_float(
            table,
            "confidence_threshold",
            path,
            budget.confidence_threshold,
        ),
        low_confidence_fallback=_optional_fallback(
            table,
            "low_confidence_fallback",
            path,
            budget.low_confidence_fallback,
        ),
        high_risk_escalation_allowed=_optional_bool(
            table,
            "high_risk_escalation_allowed",
            path,
            default=budget.high_risk_escalation_allowed,
        ),
        uncertain_escalation_allowed=_optional_bool(
            table,
            "uncertain_escalation_allowed",
            path,
            default=budget.uncertain_escalation_allowed,
        ),
        enqueue_only=_optional_bool(table, "enqueue_only", path, default=budget.enqueue_only),
    )


def _optional_int(table: TomlTable, key: str, path: str, default: int) -> int:
    if key not in table:
        return default
    return parse_int(table[key], f"{path}.{key}")


def _optional_float(table: TomlTable, key: str, path: str, default: float) -> float:
    if key not in table:
        return default
    return parse_float(table[key], f"{path}.{key}")


def _optional_bool(table: TomlTable, key: str, path: str, *, default: bool) -> bool:
    if key not in table:
        return default
    return parse_bool(table[key], f"{path}.{key}")


def _optional_fallback(
    table: TomlTable,
    key: str,
    path: str,
    default: CascadeFallbackBehavior,
) -> CascadeFallbackBehavior:
    if key not in table:
        return default
    return _parse_fallback(table[key], f"{path}.{key}")


def _validate_feature_budget(
    budget: RuntimeFeatureModelCallBudget,
    site: ModelCallSite,
) -> RuntimeFeatureModelCallBudget:
    path = f"model_call_budget.{site.value}"
    value = RuntimeFeatureModelCallBudget(
        large_llm_max_calls=_require_non_negative_int(
            budget.large_llm_max_calls,
            f"{path}.large_llm_max_calls",
        ),
        small_classifier_max_calls=_require_non_negative_int(
            budget.small_classifier_max_calls,
            f"{path}.small_classifier_max_calls",
        ),
        embedding_max_calls=_require_non_negative_int(
            budget.embedding_max_calls,
            f"{path}.embedding_max_calls",
        ),
        reranker_max_calls=_require_non_negative_int(
            budget.reranker_max_calls,
            f"{path}.reranker_max_calls",
        ),
        background_llm_max_calls=_require_non_negative_int(
            budget.background_llm_max_calls,
            f"{path}.background_llm_max_calls",
        ),
        confidence_threshold=_require_probability(
            budget.confidence_threshold,
            f"{path}.confidence_threshold",
        ),
        low_confidence_fallback=budget.low_confidence_fallback,
        high_risk_escalation_allowed=budget.high_risk_escalation_allowed,
        uncertain_escalation_allowed=budget.uncertain_escalation_allowed,
        enqueue_only=budget.enqueue_only,
    )
    _validate_site_invariants(value, site, path)
    return value


def _validate_site_invariants(
    budget: RuntimeFeatureModelCallBudget,
    site: ModelCallSite,
    path: str,
) -> None:
    if site is ModelCallSite.USER_RESPONSE_HOT_PATH and budget.large_llm_max_calls > 1:
        message = f"{path}.large_llm_max_calls must be <= 1 for user-facing hot path"
        raise ConfigError(message)
    if site is ModelCallSite.RUNTIME_LEARNING_HOOK and not budget.enqueue_only:
        message = f"{path}.enqueue_only must be true"
        raise ConfigError(message)
    if site is ModelCallSite.RUNTIME_LEARNING_HOOK and budget.large_llm_max_calls > 0:
        message = f"{path}.large_llm_max_calls must be 0 for enqueue-only runtime hooks"
        raise ConfigError(message)


def _require_non_negative_int(value: int, path: str) -> int:
    if value < 0:
        message = f"{path} must be greater than or equal to 0"
        raise ConfigError(message)
    return value


def _require_probability(value: float, path: str) -> float:
    if not 0.0 <= value <= 1.0:
        message = f"{path} must be between 0.0 and 1.0"
        raise ConfigError(message)
    return value


def _parse_fallback(value: TomlValue, path: str) -> CascadeFallbackBehavior:
    raw = parse_string(value, path)
    try:
        return CascadeFallbackBehavior(raw)
    except ValueError:
        allowed = ", ".join(item.value for item in CascadeFallbackBehavior)
        message = f"Invalid {path}: {raw}. Allowed values: {allowed}"
        raise ConfigError(message) from None
