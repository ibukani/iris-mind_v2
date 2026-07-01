"""配送後学習とバックグラウンドジョブのランタイム設定。"""

from __future__ import annotations

from dataclasses import dataclass, replace

from iris.runtime.config.parsing import TomlTable, parse_bool, parse_float, parse_int
from iris.runtime.config.validation import require_greater_than_zero


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
    return validate_learning_config(_apply_implicit_candidate_toml(value, table))


def _apply_implicit_candidate_toml(
    config: RuntimeLearningConfig,
    table: TomlTable,
) -> RuntimeLearningConfig:
    """Apply implicit candidate learning TOML values.

    Returns:
        Updated learning config.
    """
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


def validate_learning_config(config: RuntimeLearningConfig) -> RuntimeLearningConfig:
    """学習設定の数値範囲を検証する。

    Returns:
        検証済み学習設定。
    """
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
    )
