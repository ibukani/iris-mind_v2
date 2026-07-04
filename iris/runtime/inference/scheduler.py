"""ローカル推論資源の軽量 non-blocking scheduler。"""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

from iris.core.datetime_utils import now_utc
from iris.runtime.inference.models import (
    InferenceLeaseDecision,
    InferenceLeaseRequest,
    InferenceLeaseResult,
    InferenceResourceSnapshot,
    InferenceResourceState,
    InferenceSlotKind,
    InferenceWorkPriority,
)
from iris.runtime.inference.policy import LocalInferenceResourcePolicy

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

_LARGE_SLOT_KINDS = frozenset({InferenceSlotKind.LARGE_LLM, InferenceSlotKind.BACKGROUND_LLM})
_HIGH_PRIORITIES = frozenset(
    {
        InferenceWorkPriority.USER_FACING_RESPONSE,
        InferenceWorkPriority.SAFETY_CRITICAL,
    }
)
_LOW_PRIORITIES = frozenset({InferenceWorkPriority.BACKGROUND, InferenceWorkPriority.PROACTIVE})


@dataclass(frozen=True)
class _ActiveLease:
    lease_id: str
    request: InferenceLeaseRequest
    acquired_at: datetime


class LocalInferenceResourceScheduler:
    """provider 非依存の推論資源 lease boundary。

    本 scheduler は OS-level / GPU process scheduling を行わない。hot path では
    blocking wait せず、acquire / defer / cancel / no-send / denied を即時に返す。
    """

    def __init__(
        self,
        policy: LocalInferenceResourcePolicy | None = None,
        *,
        now: Callable[[], datetime] = now_utc,
    ) -> None:
        """Policy と時刻 provider を明示注入する。"""
        self._policy = policy or LocalInferenceResourcePolicy()
        self._now = now
        self._lock = asyncio.Lock()
        self._state_override: InferenceResourceState | None = None
        self._active_leases: dict[str, _ActiveLease] = {}
        self._busy_since: datetime | None = None

    @property
    def policy(self) -> LocalInferenceResourcePolicy:
        """現在の推論資源 policy を返す。"""
        return self._policy

    async def set_state(self, state: InferenceResourceState) -> None:
        """Readiness / warmup 側から見える resource state を更新する。"""
        async with self._lock:
            if state is InferenceResourceState.BUSY:
                self._state_override = InferenceResourceState.BUSY
                if self._busy_since is None:
                    self._busy_since = self._now()
                return
            self._state_override = None if state is InferenceResourceState.IDLE else state
            if state is InferenceResourceState.IDLE and not self._active_leases:
                self._busy_since = None

    async def snapshot(self) -> InferenceResourceSnapshot:
        """現在の resource snapshot を返す。

        Returns:
            InferenceResourceSnapshot: active slot と busy duration の snapshot。
        """
        async with self._lock:
            return self._snapshot_locked(self._now())

    async def acquire(self, request: InferenceLeaseRequest) -> InferenceLeaseResult:
        """推論資源 lease を non-blocking に取得する。

        Returns:
            InferenceLeaseResult: 実行可否と観測可能な理由。
        """
        async with self._lock:
            return self._acquire_locked_by_policy(request, self._now())

    def _acquire_locked_by_policy(
        self,
        request: InferenceLeaseRequest,
        current_time: datetime,
    ) -> InferenceLeaseResult:
        if not self._policy.enabled:
            return self._acquire_locked(
                request,
                current_time,
                reason="inference scheduler disabled",
            )
        state_rejection = self._state_rejection_locked(request, current_time)
        if state_rejection is not None:
            return state_rejection
        return self._capacity_decision_locked(request, current_time)

    def _state_rejection_locked(
        self,
        request: InferenceLeaseRequest,
        current_time: datetime,
    ) -> InferenceLeaseResult | None:
        state = self._state_locked()
        if state is InferenceResourceState.UNAVAILABLE:
            return self._reject_locked(
                request,
                self._policy.unavailable_decision_for(request.priority),
                "local inference resource unavailable",
                current_time,
            )
        if state is InferenceResourceState.WARMING and request.priority in _LOW_PRIORITIES:
            return self._reject_locked(
                request,
                self._policy.low_priority_when_warming,
                "local inference resource warming",
                current_time,
            )
        if self._explicit_large_model_busy(request):
            return self._reject_locked(
                request,
                self._busy_decision_for(request),
                "local inference resource busy",
                current_time,
            )
        return None

    def _capacity_decision_locked(
        self,
        request: InferenceLeaseRequest,
        current_time: datetime,
    ) -> InferenceLeaseResult:
        capacity_reason = self._capacity_reason(request)
        if capacity_reason is None:
            return self._acquire_locked(request, current_time, reason="resource lease acquired")
        cancelled = self._preempt_lower_priority_large_leases(request)
        if cancelled:
            reason = (
                f"resource lease acquired after preempting {len(cancelled)} low priority lease(s)"
            )
            return self._acquire_locked(
                request,
                current_time,
                reason=reason,
                cancelled_lease_ids=cancelled,
            )
        return self._reject_locked(
            request,
            self._busy_decision_for(request),
            capacity_reason,
            current_time,
        )

    def _busy_decision_for(self, request: InferenceLeaseRequest) -> InferenceLeaseDecision:
        if request.priority in _HIGH_PRIORITIES:
            return InferenceLeaseDecision.DEFER
        return self._policy.busy_decision_for(request.priority)

    def _explicit_large_model_busy(self, request: InferenceLeaseRequest) -> bool:
        return (
            self._state_override is InferenceResourceState.BUSY
            and request.slot_kind in _LARGE_SLOT_KINDS
        )

    async def release(self, lease_id: str) -> bool:
        """Lease を解放する。preempt 済み lease の release は no-op にする。

        Returns:
            bool: active lease を解放した場合 True。
        """
        async with self._lock:
            removed = self._active_leases.pop(lease_id, None)
            if removed is None:
                return False
            if not self._active_leases and self._state_override is None:
                self._busy_since = None
            return True

    def _state_locked(self) -> InferenceResourceState:
        if self._state_override is not None:
            return self._state_override
        if self._active_leases:
            return InferenceResourceState.BUSY
        return InferenceResourceState.IDLE

    def _snapshot_locked(self, current_time: datetime) -> InferenceResourceSnapshot:
        counts = Counter(lease.request.slot_kind for lease in self._active_leases.values())
        active_large_slots = sum(counts[kind] for kind in _LARGE_SLOT_KINDS)
        busy_since = (
            self._busy_since if self._state_locked() is InferenceResourceState.BUSY else None
        )
        busy_duration = None if busy_since is None else (current_time - busy_since).total_seconds()
        return InferenceResourceSnapshot(
            state=self._state_locked(),
            active_large_slots=active_large_slots,
            active_small_classifier_slots=counts[InferenceSlotKind.SMALL_CLASSIFIER],
            active_embedding_slots=counts[InferenceSlotKind.EMBEDDING],
            active_reranker_slots=counts[InferenceSlotKind.RERANKER],
            busy_since=busy_since,
            busy_duration_seconds=busy_duration,
        )

    def _capacity_reason(self, request: InferenceLeaseRequest) -> str | None:
        counts = Counter(lease.request.slot_kind for lease in self._active_leases.values())
        reason: str | None = None
        if request.slot_kind in _LARGE_SLOT_KINDS:
            active_large = sum(counts[kind] for kind in _LARGE_SLOT_KINDS)
            if active_large >= self._policy.large_llm_concurrency_limit:
                reason = "large LLM slot limit reached"
        elif (
            request.slot_kind is InferenceSlotKind.SMALL_CLASSIFIER
            and counts[request.slot_kind] >= self._policy.small_classifier_concurrency_limit
        ):
            reason = "small classifier slot limit reached"
        elif (
            request.slot_kind is InferenceSlotKind.EMBEDDING
            and counts[request.slot_kind] >= self._policy.embedding_concurrency_limit
        ):
            reason = "embedding slot limit reached"
        elif (
            request.slot_kind is InferenceSlotKind.RERANKER
            and counts[request.slot_kind] >= self._policy.reranker_concurrency_limit
        ):
            reason = "reranker slot limit reached"
        return reason

    def _preempt_lower_priority_large_leases(
        self,
        request: InferenceLeaseRequest,
    ) -> tuple[str, ...]:
        if not self._policy.preempt_background_for_user_facing:
            return ()
        if request.priority not in _HIGH_PRIORITIES or request.slot_kind not in _LARGE_SLOT_KINDS:
            return ()
        cancellable = tuple(
            lease_id
            for lease_id, lease in self._active_leases.items()
            if (
                lease.request.slot_kind in _LARGE_SLOT_KINDS
                and lease.request.priority in _LOW_PRIORITIES
            )
        )
        for lease_id in cancellable:
            self._active_leases.pop(lease_id, None)
        return cancellable

    def _acquire_locked(
        self,
        request: InferenceLeaseRequest,
        current_time: datetime,
        *,
        reason: str,
        cancelled_lease_ids: tuple[str, ...] = (),
    ) -> InferenceLeaseResult:
        lease_id = str(uuid4())
        self._active_leases[lease_id] = _ActiveLease(
            lease_id=lease_id,
            request=request,
            acquired_at=current_time,
        )
        if self._busy_since is None:
            self._busy_since = current_time
        return InferenceLeaseResult(
            decision=InferenceLeaseDecision.ACQUIRED,
            reason=reason,
            request=request,
            snapshot=self._snapshot_locked(current_time),
            lease_id=lease_id,
            cancelled_lease_ids=cancelled_lease_ids,
        )

    def _reject_locked(
        self,
        request: InferenceLeaseRequest,
        decision: InferenceLeaseDecision,
        reason: str,
        current_time: datetime,
    ) -> InferenceLeaseResult:
        return InferenceLeaseResult(
            decision=decision,
            reason=reason,
            request=request,
            snapshot=self._snapshot_locked(current_time),
        )
