"""配送後学習とバックグラウンドジョブのランタイム設定。"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.parsing import (
    TomlTable,
    parse_bool,
    parse_float,
    parse_int,
    parse_string,
    table_or_empty,
)
from iris.runtime.config.validation import require_greater_than_zero
from iris.runtime.learning.policy import BackgroundJobBackpressureMode


@dataclass(frozen=True)
class RuntimeBackgroundJobKindPolicyConfig:
    """単一 background job kind の runtime config。"""

    concurrency_limit: int = 1
    timeout_seconds: float = 30.0
    max_pending_jobs: int = 100
    uses_llm: bool = False
    idle_only: bool = False


@dataclass(frozen=True)
class RuntimeBackgroundJobKindsPolicyConfig:
    """BackgroundJobQueue pressure policy の kind 別 runtime config。"""

    memory_extraction: RuntimeBackgroundJobKindPolicyConfig = field(
        default_factory=lambda: RuntimeBackgroundJobKindPolicyConfig(uses_llm=True)
    )
    reflection: RuntimeBackgroundJobKindPolicyConfig = field(
        default_factory=lambda: RuntimeBackgroundJobKindPolicyConfig(
            timeout_seconds=60.0,
            max_pending_jobs=50,
            uses_llm=True,
            idle_only=True,
        )
    )


@dataclass(frozen=True)
class RuntimeBackgroundJobPolicyConfig:
    """BackgroundJobQueue pressure policy の runtime config。"""

    enabled: bool = False
    default_concurrency_limit: int = 1
    default_timeout_seconds: float = 30.0
    default_max_pending_jobs: int = 100
    retry_backoff_base_seconds: float = 30.0
    retry_backoff_max_seconds: float = 1800.0
    defer_seconds_when_saturated: float = 30.0
    backpressure_mode: str = BackgroundJobBackpressureMode.DEFER.value
    kinds: RuntimeBackgroundJobKindsPolicyConfig = field(
        default_factory=RuntimeBackgroundJobKindsPolicyConfig
    )


@dataclass(frozen=True)
class RuntimeLearningConfig:
    """学習 dispatch と background loop の設定。"""

    enabled: bool = True
    background_jobs_enabled: bool = True
    background_job_interval_seconds: float = 10.0
    max_jobs_per_run: int = 5
    max_attempts: int = 3
    implicit_candidates_enabled: bool = True
    implicit_candidate_min_confidence: float = 0.35
    implicit_candidate_max_text_length: int = 1000
    background_job_policy: RuntimeBackgroundJobPolicyConfig = field(
        default_factory=RuntimeBackgroundJobPolicyConfig
    )


def apply_learning_toml(
    config: RuntimeLearningConfig,
    table: TomlTable,
) -> RuntimeLearningConfig:
    """`[learning]` TOML 値を適用する。

    Returns:
        検証済み学習設定。
    """
    value = config
    if "enabled" in table:
        value = replace(value, enabled=parse_bool(table["enabled"], "learning.enabled"))
    if "background_jobs_enabled" in table:
        value = replace(
            value,
            background_jobs_enabled=parse_bool(
                table["background_jobs_enabled"],
                "learning.background_jobs_enabled",
            ),
        )
    if "background_job_interval_seconds" in table:
        value = replace(
            value,
            background_job_interval_seconds=parse_float(
                table["background_job_interval_seconds"],
                "learning.background_job_interval_seconds",
            ),
        )
    if "max_jobs_per_run" in table:
        value = replace(
            value,
            max_jobs_per_run=parse_int(table["max_jobs_per_run"], "learning.max_jobs_per_run"),
        )
    if "max_attempts" in table:
        value = replace(
            value,
            max_attempts=parse_int(table["max_attempts"], "learning.max_attempts"),
        )
    value = _apply_implicit_candidate_toml(value, table)
    value = _apply_background_job_policy_toml(value, table)
    return validate_learning_config(value)


def _apply_implicit_candidate_toml(
    config: RuntimeLearningConfig,
    table: TomlTable,
) -> RuntimeLearningConfig:
    value = config
    if "implicit_candidates_enabled" in table:
        value = replace(
            value,
            implicit_candidates_enabled=parse_bool(
                table["implicit_candidates_enabled"],
                "learning.implicit_candidates_enabled",
            ),
        )
    if "implicit_candidate_min_confidence" in table:
        value = replace(
            value,
            implicit_candidate_min_confidence=parse_float(
                table["implicit_candidate_min_confidence"],
                "learning.implicit_candidate_min_confidence",
            ),
        )
    if "implicit_candidate_max_text_length" in table:
        value = replace(
            value,
            implicit_candidate_max_text_length=parse_int(
                table["implicit_candidate_max_text_length"],
                "learning.implicit_candidate_max_text_length",
            ),
        )
    return value


def _apply_background_job_policy_toml(
    config: RuntimeLearningConfig,
    table: TomlTable,
) -> RuntimeLearningConfig:
    policy_table = table_or_empty(
        table,
        "background_job_policy",
        path="learning.background_job_policy",
    )
    if not policy_table:
        return config
    policy = _apply_background_job_policy_fields(
        config.background_job_policy,
        policy_table,
        path="learning.background_job_policy",
    )
    kinds_table = table_or_empty(
        policy_table,
        "kinds",
        path="learning.background_job_policy.kinds",
    )
    policy = _apply_known_kind_policy(policy, kinds_table, "memory_extraction")
    policy = _apply_known_kind_policy(policy, kinds_table, "reflection")
    _reject_unknown_kind_tables(kinds_table)
    return replace(config, background_job_policy=policy)


def _apply_background_job_policy_fields(
    policy: RuntimeBackgroundJobPolicyConfig,
    table: TomlTable,
    *,
    path: str,
) -> RuntimeBackgroundJobPolicyConfig:
    value = policy
    if "enabled" in table:
        value = replace(value, enabled=parse_bool(table["enabled"], f"{path}.enabled"))
    if "default_concurrency_limit" in table:
        value = replace(
            value,
            default_concurrency_limit=parse_int(
                table["default_concurrency_limit"],
                f"{path}.default_concurrency_limit",
            ),
        )
    if "default_timeout_seconds" in table:
        value = replace(
            value,
            default_timeout_seconds=parse_float(
                table["default_timeout_seconds"],
                f"{path}.default_timeout_seconds",
            ),
        )
    if "default_max_pending_jobs" in table:
        value = replace(
            value,
            default_max_pending_jobs=parse_int(
                table["default_max_pending_jobs"],
                f"{path}.default_max_pending_jobs",
            ),
        )
    value = _apply_background_job_policy_float_fields(value, table, path=path)
    if "backpressure_mode" in table:
        value = replace(
            value,
            backpressure_mode=_parse_backpressure_mode(
                parse_string(table["backpressure_mode"], f"{path}.backpressure_mode")
            ).value,
        )
    return value


def _apply_background_job_policy_float_fields(
    policy: RuntimeBackgroundJobPolicyConfig,
    table: TomlTable,
    *,
    path: str,
) -> RuntimeBackgroundJobPolicyConfig:
    value = policy
    if "retry_backoff_base_seconds" in table:
        value = replace(
            value,
            retry_backoff_base_seconds=parse_float(
                table["retry_backoff_base_seconds"],
                f"{path}.retry_backoff_base_seconds",
            ),
        )
    if "retry_backoff_max_seconds" in table:
        value = replace(
            value,
            retry_backoff_max_seconds=parse_float(
                table["retry_backoff_max_seconds"],
                f"{path}.retry_backoff_max_seconds",
            ),
        )
    if "defer_seconds_when_saturated" in table:
        value = replace(
            value,
            defer_seconds_when_saturated=parse_float(
                table["defer_seconds_when_saturated"],
                f"{path}.defer_seconds_when_saturated",
            ),
        )
    return value


def _apply_known_kind_policy(
    policy: RuntimeBackgroundJobPolicyConfig,
    kinds_table: TomlTable,
    kind_key: str,
) -> RuntimeBackgroundJobPolicyConfig:
    if kind_key == "memory_extraction":
        return _apply_memory_extraction_policy(policy, kinds_table)
    return _apply_reflection_policy(policy, kinds_table)


def _apply_memory_extraction_policy(
    policy: RuntimeBackgroundJobPolicyConfig,
    kinds_table: TomlTable,
) -> RuntimeBackgroundJobPolicyConfig:
    kind_table = table_or_empty(
        kinds_table,
        "memory_extraction",
        path="learning.background_job_policy.kinds.memory_extraction",
    )
    if not kind_table:
        return policy
    updated = _apply_kind_policy_fields(
        policy.kinds.memory_extraction,
        kind_table,
        path="learning.background_job_policy.kinds.memory_extraction",
    )
    return replace(policy, kinds=replace(policy.kinds, memory_extraction=updated))


def _apply_reflection_policy(
    policy: RuntimeBackgroundJobPolicyConfig,
    kinds_table: TomlTable,
) -> RuntimeBackgroundJobPolicyConfig:
    kind_table = table_or_empty(
        kinds_table,
        "reflection",
        path="learning.background_job_policy.kinds.reflection",
    )
    if not kind_table:
        return policy
    updated = _apply_kind_policy_fields(
        policy.kinds.reflection,
        kind_table,
        path="learning.background_job_policy.kinds.reflection",
    )
    return replace(policy, kinds=replace(policy.kinds, reflection=updated))


def _apply_kind_policy_fields(
    policy: RuntimeBackgroundJobKindPolicyConfig,
    table: TomlTable,
    *,
    path: str,
) -> RuntimeBackgroundJobKindPolicyConfig:
    value = policy
    if "concurrency_limit" in table:
        value = replace(
            value,
            concurrency_limit=parse_int(table["concurrency_limit"], f"{path}.concurrency_limit"),
        )
    if "timeout_seconds" in table:
        value = replace(
            value,
            timeout_seconds=parse_float(table["timeout_seconds"], f"{path}.timeout_seconds"),
        )
    if "max_pending_jobs" in table:
        value = replace(
            value,
            max_pending_jobs=parse_int(table["max_pending_jobs"], f"{path}.max_pending_jobs"),
        )
    if "uses_llm" in table:
        value = replace(value, uses_llm=parse_bool(table["uses_llm"], f"{path}.uses_llm"))
    if "idle_only" in table:
        value = replace(value, idle_only=parse_bool(table["idle_only"], f"{path}.idle_only"))
    return value


def validate_learning_config(config: RuntimeLearningConfig) -> RuntimeLearningConfig:
    """学習設定の数値範囲を検証する。

    Returns:
        検証済み学習設定。
    """
    validated_policy = _validate_background_job_policy(config.background_job_policy)
    return replace(
        config,
        background_job_interval_seconds=require_greater_than_zero(
            config.background_job_interval_seconds,
            "learning.background_job_interval_seconds",
        ),
        max_jobs_per_run=require_greater_than_zero(
            config.max_jobs_per_run,
            "learning.max_jobs_per_run",
        ),
        max_attempts=require_greater_than_zero(config.max_attempts, "learning.max_attempts"),
        implicit_candidate_min_confidence=require_greater_than_zero(
            config.implicit_candidate_min_confidence,
            "learning.implicit_candidate_min_confidence",
        ),
        implicit_candidate_max_text_length=require_greater_than_zero(
            config.implicit_candidate_max_text_length,
            "learning.implicit_candidate_max_text_length",
        ),
        background_job_policy=validated_policy,
    )


def _validate_background_job_policy(
    policy: RuntimeBackgroundJobPolicyConfig,
) -> RuntimeBackgroundJobPolicyConfig:
    validated = replace(
        policy,
        default_concurrency_limit=require_greater_than_zero(
            policy.default_concurrency_limit,
            "learning.background_job_policy.default_concurrency_limit",
        ),
        default_timeout_seconds=require_greater_than_zero(
            policy.default_timeout_seconds,
            "learning.background_job_policy.default_timeout_seconds",
        ),
        default_max_pending_jobs=require_greater_than_zero(
            policy.default_max_pending_jobs,
            "learning.background_job_policy.default_max_pending_jobs",
        ),
        retry_backoff_base_seconds=require_greater_than_zero(
            policy.retry_backoff_base_seconds,
            "learning.background_job_policy.retry_backoff_base_seconds",
        ),
        retry_backoff_max_seconds=require_greater_than_zero(
            policy.retry_backoff_max_seconds,
            "learning.background_job_policy.retry_backoff_max_seconds",
        ),
        defer_seconds_when_saturated=require_greater_than_zero(
            policy.defer_seconds_when_saturated,
            "learning.background_job_policy.defer_seconds_when_saturated",
        ),
        kinds=RuntimeBackgroundJobKindsPolicyConfig(
            memory_extraction=_validate_kind_policy(
                policy.kinds.memory_extraction,
                path="learning.background_job_policy.kinds.memory_extraction",
            ),
            reflection=_validate_kind_policy(
                policy.kinds.reflection,
                path="learning.background_job_policy.kinds.reflection",
            ),
        ),
    )
    if validated.retry_backoff_max_seconds < validated.retry_backoff_base_seconds:
        message = (
            "learning.background_job_policy.retry_backoff_max_seconds must be greater than or "
            "equal to learning.background_job_policy.retry_backoff_base_seconds"
        )
        raise ConfigError(message)
    return replace(
        validated,
        backpressure_mode=_parse_backpressure_mode(validated.backpressure_mode).value,
    )


def _validate_kind_policy(
    policy: RuntimeBackgroundJobKindPolicyConfig,
    *,
    path: str,
) -> RuntimeBackgroundJobKindPolicyConfig:
    return replace(
        policy,
        concurrency_limit=require_greater_than_zero(
            policy.concurrency_limit,
            f"{path}.concurrency_limit",
        ),
        timeout_seconds=require_greater_than_zero(
            policy.timeout_seconds,
            f"{path}.timeout_seconds",
        ),
        max_pending_jobs=require_greater_than_zero(
            policy.max_pending_jobs,
            f"{path}.max_pending_jobs",
        ),
    )


def _reject_unknown_kind_tables(kinds_table: TomlTable) -> None:
    for key in kinds_table:
        if key not in {"memory_extraction", "reflection"}:
            message = f"unknown background job kind config: {key}"
            raise ConfigError(message)


def _parse_backpressure_mode(value: str) -> BackgroundJobBackpressureMode:
    try:
        return BackgroundJobBackpressureMode(value)
    except ValueError as exc:
        message = f"unknown background job backpressure mode: {value}"
        raise ConfigError(message) from exc
