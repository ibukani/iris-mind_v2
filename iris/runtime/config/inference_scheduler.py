"""ローカル推論資源 scheduler の runtime config。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.parsing import parse_bool, parse_int, parse_string
from iris.runtime.config.validation import require_greater_than_zero
from iris.runtime.inference.models import InferenceLeaseDecision
from iris.runtime.inference.policy import LocalInferenceResourcePolicy

if TYPE_CHECKING:
    from iris.runtime.config.parsing import TomlTable


class RuntimeInferenceSchedulerBusyBehavior(StrEnum):
    """低優先度 work が busy 資源に遭遇した時の挙動。"""

    DEFER = "defer"
    CANCEL = "cancel"
    NO_SEND = "no_send"


class RuntimeInferenceSchedulerUnavailableBehavior(StrEnum):
    """unavailable 資源に遭遇した時の挙動。"""

    DEFER = "defer"
    CANCEL = "cancel"
    NO_SEND = "no_send"
    DENIED = "denied"


@dataclass(frozen=True)
class RuntimeInferenceSchedulerConfig:
    """ローカル推論資源 lease boundary の有効化と policy knobs。"""

    enabled: bool = False
    large_llm_concurrency_limit: int = 1
    small_classifier_concurrency_limit: int = 4
    embedding_concurrency_limit: int = 2
    reranker_concurrency_limit: int = 2
    preempt_background_for_user_facing: bool = True
    background_when_busy: RuntimeInferenceSchedulerBusyBehavior = (
        RuntimeInferenceSchedulerBusyBehavior.DEFER
    )
    proactive_when_busy: RuntimeInferenceSchedulerBusyBehavior = (
        RuntimeInferenceSchedulerBusyBehavior.NO_SEND
    )
    low_priority_when_warming: RuntimeInferenceSchedulerBusyBehavior = (
        RuntimeInferenceSchedulerBusyBehavior.DEFER
    )
    background_when_unavailable: RuntimeInferenceSchedulerUnavailableBehavior = (
        RuntimeInferenceSchedulerUnavailableBehavior.CANCEL
    )
    proactive_when_unavailable: RuntimeInferenceSchedulerUnavailableBehavior = (
        RuntimeInferenceSchedulerUnavailableBehavior.NO_SEND
    )
    user_facing_when_unavailable: RuntimeInferenceSchedulerUnavailableBehavior = (
        RuntimeInferenceSchedulerUnavailableBehavior.DENIED
    )

    def to_policy(self) -> LocalInferenceResourcePolicy:
        """Runtime config から scheduler policy を構築する。

        Returns:
            LocalInferenceResourcePolicy: scheduler が利用する policy。
        """
        return LocalInferenceResourcePolicy(
            enabled=self.enabled,
            large_llm_concurrency_limit=self.large_llm_concurrency_limit,
            small_classifier_concurrency_limit=self.small_classifier_concurrency_limit,
            embedding_concurrency_limit=self.embedding_concurrency_limit,
            reranker_concurrency_limit=self.reranker_concurrency_limit,
            preempt_background_for_user_facing=self.preempt_background_for_user_facing,
            background_when_busy=_busy_behavior_to_decision(self.background_when_busy),
            proactive_when_busy=_busy_behavior_to_decision(self.proactive_when_busy),
            low_priority_when_warming=_busy_behavior_to_decision(self.low_priority_when_warming),
            background_when_unavailable=_unavailable_behavior_to_decision(
                self.background_when_unavailable
            ),
            proactive_when_unavailable=_unavailable_behavior_to_decision(
                self.proactive_when_unavailable
            ),
            user_facing_when_unavailable=_unavailable_behavior_to_decision(
                self.user_facing_when_unavailable
            ),
        )


def apply_inference_scheduler_toml(
    config: RuntimeInferenceSchedulerConfig,
    table: TomlTable,
) -> RuntimeInferenceSchedulerConfig:
    """`[inference_scheduler]` effective TOML を適用する。

    Returns:
        検証済み scheduler config。
    """
    value = config
    if "enabled" in table:
        value = replace(value, enabled=parse_bool(table["enabled"], "inference_scheduler.enabled"))
    if "large_llm_concurrency_limit" in table:
        value = replace(
            value,
            large_llm_concurrency_limit=parse_int(
                table["large_llm_concurrency_limit"],
                "inference_scheduler.large_llm_concurrency_limit",
            ),
        )
    if "small_classifier_concurrency_limit" in table:
        value = replace(
            value,
            small_classifier_concurrency_limit=parse_int(
                table["small_classifier_concurrency_limit"],
                "inference_scheduler.small_classifier_concurrency_limit",
            ),
        )
    if "embedding_concurrency_limit" in table:
        value = replace(
            value,
            embedding_concurrency_limit=parse_int(
                table["embedding_concurrency_limit"],
                "inference_scheduler.embedding_concurrency_limit",
            ),
        )
    if "reranker_concurrency_limit" in table:
        value = replace(
            value,
            reranker_concurrency_limit=parse_int(
                table["reranker_concurrency_limit"],
                "inference_scheduler.reranker_concurrency_limit",
            ),
        )
    value = _apply_behavior_toml(value, table)
    return validate_inference_scheduler_config(value)


def _apply_behavior_toml(
    config: RuntimeInferenceSchedulerConfig,
    table: TomlTable,
) -> RuntimeInferenceSchedulerConfig:
    value = config
    if "preempt_background_for_user_facing" in table:
        value = replace(
            value,
            preempt_background_for_user_facing=parse_bool(
                table["preempt_background_for_user_facing"],
                "inference_scheduler.preempt_background_for_user_facing",
            ),
        )
    if "background_when_busy" in table:
        value = replace(
            value,
            background_when_busy=_parse_busy_behavior(
                parse_string(
                    table["background_when_busy"],
                    "inference_scheduler.background_when_busy",
                )
            ),
        )
    if "proactive_when_busy" in table:
        value = replace(
            value,
            proactive_when_busy=_parse_busy_behavior(
                parse_string(
                    table["proactive_when_busy"],
                    "inference_scheduler.proactive_when_busy",
                )
            ),
        )
    if "low_priority_when_warming" in table:
        value = replace(
            value,
            low_priority_when_warming=_parse_busy_behavior(
                parse_string(
                    table["low_priority_when_warming"],
                    "inference_scheduler.low_priority_when_warming",
                )
            ),
        )
    if "background_when_unavailable" in table:
        value = replace(
            value,
            background_when_unavailable=_parse_unavailable_behavior(
                parse_string(
                    table["background_when_unavailable"],
                    "inference_scheduler.background_when_unavailable",
                )
            ),
        )
    if "proactive_when_unavailable" in table:
        value = replace(
            value,
            proactive_when_unavailable=_parse_unavailable_behavior(
                parse_string(
                    table["proactive_when_unavailable"],
                    "inference_scheduler.proactive_when_unavailable",
                )
            ),
        )
    if "user_facing_when_unavailable" in table:
        value = replace(
            value,
            user_facing_when_unavailable=_parse_unavailable_behavior(
                parse_string(
                    table["user_facing_when_unavailable"],
                    "inference_scheduler.user_facing_when_unavailable",
                )
            ),
        )
    return value


def validate_inference_scheduler_config(
    config: RuntimeInferenceSchedulerConfig,
) -> RuntimeInferenceSchedulerConfig:
    """Scheduler config の数値制約を検証する。

    Returns:
        検証済み config。

    Raises:
        ConfigError: 数値上限が Issue #93 の制約に反する場合。
    """
    large_limit = require_greater_than_zero(
        config.large_llm_concurrency_limit,
        "inference_scheduler.large_llm_concurrency_limit",
    )
    if large_limit != 1:
        message = "inference_scheduler.large_llm_concurrency_limit must be 1"
        raise ConfigError(message)
    return replace(
        config,
        large_llm_concurrency_limit=large_limit,
        small_classifier_concurrency_limit=require_greater_than_zero(
            config.small_classifier_concurrency_limit,
            "inference_scheduler.small_classifier_concurrency_limit",
        ),
        embedding_concurrency_limit=require_greater_than_zero(
            config.embedding_concurrency_limit,
            "inference_scheduler.embedding_concurrency_limit",
        ),
        reranker_concurrency_limit=require_greater_than_zero(
            config.reranker_concurrency_limit,
            "inference_scheduler.reranker_concurrency_limit",
        ),
    )


def inference_scheduler_busy_behavior_values() -> tuple[str, ...]:
    """Busy behavior enum value 群を返す。

    Returns:
        busy behavior の TOML value 群。
    """
    return tuple(item.value for item in RuntimeInferenceSchedulerBusyBehavior)


def inference_scheduler_unavailable_behavior_values() -> tuple[str, ...]:
    """Unavailable behavior enum value 群を返す。

    Returns:
        unavailable behavior の TOML value 群。
    """
    return tuple(item.value for item in RuntimeInferenceSchedulerUnavailableBehavior)


def _parse_busy_behavior(value: str) -> RuntimeInferenceSchedulerBusyBehavior:
    try:
        return RuntimeInferenceSchedulerBusyBehavior(value)
    except ValueError as exc:
        message = f"Unknown inference scheduler busy behavior: {value}"
        raise ConfigError(message) from exc


def _parse_unavailable_behavior(value: str) -> RuntimeInferenceSchedulerUnavailableBehavior:
    try:
        return RuntimeInferenceSchedulerUnavailableBehavior(value)
    except ValueError as exc:
        message = f"Unknown inference scheduler unavailable behavior: {value}"
        raise ConfigError(message) from exc


def _busy_behavior_to_decision(
    value: RuntimeInferenceSchedulerBusyBehavior,
) -> InferenceLeaseDecision:
    if value is RuntimeInferenceSchedulerBusyBehavior.DEFER:
        return InferenceLeaseDecision.DEFER
    if value is RuntimeInferenceSchedulerBusyBehavior.CANCEL:
        return InferenceLeaseDecision.CANCEL
    return InferenceLeaseDecision.NO_SEND


def _unavailable_behavior_to_decision(
    value: RuntimeInferenceSchedulerUnavailableBehavior,
) -> InferenceLeaseDecision:
    if value is RuntimeInferenceSchedulerUnavailableBehavior.DEFER:
        return InferenceLeaseDecision.DEFER
    if value is RuntimeInferenceSchedulerUnavailableBehavior.CANCEL:
        return InferenceLeaseDecision.CANCEL
    if value is RuntimeInferenceSchedulerUnavailableBehavior.NO_SEND:
        return InferenceLeaseDecision.NO_SEND
    return InferenceLeaseDecision.DENIED
