"""BackgroundJobQueue の圧力制御 policy と metrics 型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from iris.runtime.learning.jobs import BackgroundJobRecord

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from iris.runtime.learning.jobs import BackgroundJobKind


class BackgroundJobBackpressureMode(StrEnum):
    """Kind pressure 発生時の enqueue 方針。"""

    ACCEPT = "accept"
    DEFER = "defer"
    REJECT = "reject"


class BackgroundJobEnqueueDecision(StrEnum):
    """enqueue_with_policy の結果。"""

    ACCEPTED = "accepted"
    EXISTING = "existing"
    DEFERRED = "deferred"
    REJECTED = "rejected"


class BackgroundJobBackpressureReason(StrEnum):
    """enqueue defer / reject の観測可能な理由。"""

    MAX_PENDING_JOBS = "max_pending_jobs"
    KIND_CONCURRENCY_SATURATED = "kind_concurrency_saturated"
    IDLE_ONLY_NOT_AVAILABLE = "idle_only_not_available"
    RETRY_STORM_PREVENTION = "retry_storm_prevention"


@dataclass(frozen=True)
class BackgroundJobKindPolicy:
    """単一 job kind に適用する queue pressure policy。"""

    concurrency_limit: int = 1
    timeout_seconds: float = 30.0
    max_pending_jobs: int = 100
    retry_backoff_base_seconds: float = 30.0
    retry_backoff_max_seconds: float = 1800.0
    defer_seconds_when_saturated: float = 30.0
    backpressure_mode: BackgroundJobBackpressureMode = BackgroundJobBackpressureMode.DEFER
    uses_llm: bool = False
    idle_only: bool = False

    def __post_init__(self) -> None:
        """不正な pressure policy を早期に拒否する。

        Raises:
            ValueError: 数値範囲が不正な場合。
        """
        _require_positive_int(self.concurrency_limit, "concurrency_limit")
        _require_positive_float(self.timeout_seconds, "timeout_seconds")
        _require_positive_int(self.max_pending_jobs, "max_pending_jobs")
        _require_positive_float(self.retry_backoff_base_seconds, "retry_backoff_base_seconds")
        _require_positive_float(self.retry_backoff_max_seconds, "retry_backoff_max_seconds")
        _require_positive_float(self.defer_seconds_when_saturated, "defer_seconds_when_saturated")
        if self.retry_backoff_max_seconds < self.retry_backoff_base_seconds:
            message = "retry_backoff_max_seconds must be greater than or equal to base"
            raise ValueError(message)

    def retry_delay_seconds(self, attempts_before_failure: int) -> float:
        """現在の attempts から retry storm を避ける delay 秒数を返す。

        Returns:
            retry delay 秒数。
        """
        _require_non_negative_int(attempts_before_failure, "attempts_before_failure")
        multiplier = 1.0
        for _ in range(attempts_before_failure):
            multiplier *= 2.0
        delay = self.retry_backoff_base_seconds * multiplier
        return min(delay, self.retry_backoff_max_seconds)


def _empty_per_kind_policy() -> dict[BackgroundJobKind, BackgroundJobKindPolicy]:
    return {}


@dataclass(frozen=True)
class BackgroundJobQueuePolicy:
    """BackgroundJobQueue が参照する kind 別 policy 集合。"""

    default_policy: BackgroundJobKindPolicy = field(default_factory=BackgroundJobKindPolicy)
    per_kind: Mapping[BackgroundJobKind, BackgroundJobKindPolicy] = field(
        default_factory=_empty_per_kind_policy
    )

    def for_kind(self, kind: BackgroundJobKind) -> BackgroundJobKindPolicy:
        """Job kind に対応する policy を返す。

        Returns:
            kind 固有または default policy。
        """
        return self.per_kind.get(kind, self.default_policy)


@dataclass(frozen=True)
class BackgroundJobEnqueueResult:
    """policy 適用後の enqueue 結果。"""

    decision: BackgroundJobEnqueueDecision
    record: BackgroundJobRecord | None
    reason: BackgroundJobBackpressureReason | None = None
    deferred_until: datetime | None = None


@dataclass(frozen=True)
class BackgroundJobKindMetrics:
    """単一 job kind の queue metrics。"""

    kind: BackgroundJobKind
    pending: int = 0
    leased: int = 0
    succeeded: int = 0
    failed_retryable: int = 0
    failed_permanent: int = 0
    cancelled: int = 0
    oldest_pending_age_seconds: float | None = None

    @property
    def failed(self) -> int:
        """失敗状態の合計を返す。"""
        return self.failed_retryable + self.failed_permanent

    @property
    def queue_depth(self) -> int:
        """未完了 backlog として扱う件数を返す。"""
        return self.pending + self.failed_retryable


@dataclass(frozen=True)
class BackgroundJobQueueMetrics:
    """BackgroundJobQueue 全体の metrics snapshot。"""

    generated_at: datetime
    queue_depth: int
    leased: int
    succeeded: int
    failed_retryable: int
    failed_permanent: int
    cancelled: int
    oldest_pending_age_seconds: float | None
    per_kind: tuple[BackgroundJobKindMetrics, ...]

    @property
    def failed(self) -> int:
        """失敗状態の合計を返す。"""
        return self.failed_retryable + self.failed_permanent

    @property
    def non_terminal(self) -> int:
        """完了していない job 件数を返す。"""
        return self.queue_depth + self.leased


def defer_job_record(
    job: BackgroundJobRecord,
    *,
    deferred_until: datetime,
    reason: BackgroundJobBackpressureReason,
) -> BackgroundJobRecord:
    """Enqueue defer 用に job の not_before と defer_reason を更新する。

    Returns:
        defer metadata を反映した job。
    """
    return BackgroundJobRecord(
        job_id=job.job_id,
        kind=job.kind,
        payload=job.payload,
        status=job.status,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        not_before=deferred_until,
        leased_until=job.leased_until,
        idempotency_key=job.idempotency_key,
        created_at=job.created_at,
        updated_at=deferred_until,
        last_error=job.last_error,
        resource_profile=job.resource_profile,
        defer_reason=reason.value,
    )


def _require_positive_int(value: int, name: str) -> None:
    if isinstance(value, bool) or value <= 0:
        message = f"{name} must be greater than zero"
        raise ValueError(message)


def _require_non_negative_int(value: int, name: str) -> None:
    if isinstance(value, bool) or value < 0:
        message = f"{name} must be zero or greater"
        raise ValueError(message)


def _require_positive_float(value: float, name: str) -> None:
    if isinstance(value, bool) or value <= 0:
        message = f"{name} must be greater than zero"
        raise ValueError(message)
