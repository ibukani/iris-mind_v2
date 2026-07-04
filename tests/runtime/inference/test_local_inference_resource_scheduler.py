"""LocalInferenceResourceScheduler のテスト。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.contracts.model_policy import ModelCallSite
from iris.runtime.inference.models import (
    InferenceLeaseDecision,
    InferenceLeaseRequest,
    InferenceResourceState,
    InferenceSlotKind,
    InferenceWorkPriority,
)
from iris.runtime.inference.policy import LocalInferenceResourcePolicy
from iris.runtime.inference.scheduler import LocalInferenceResourceScheduler

pytestmark = pytest.mark.anyio

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _scheduler(
    policy: LocalInferenceResourcePolicy | None = None,
) -> LocalInferenceResourceScheduler:
    return LocalInferenceResourceScheduler(
        policy=policy or LocalInferenceResourcePolicy(enabled=True),
        now=lambda: _NOW,
    )


def _request(
    *,
    priority: InferenceWorkPriority,
    slot_kind: InferenceSlotKind = InferenceSlotKind.LARGE_LLM,
    call_site: ModelCallSite = ModelCallSite.USER_RESPONSE_HOT_PATH,
) -> InferenceLeaseRequest:
    return InferenceLeaseRequest(
        slot_kind=slot_kind,
        priority=priority,
        call_site=call_site,
    )


async def test_large_llm_lease_sets_busy_and_release_returns_idle() -> None:
    """Large LLM lease は busy state を作り、release 後 idle に戻る。"""
    scheduler = _scheduler()

    result = await scheduler.acquire(_request(priority=InferenceWorkPriority.USER_FACING_RESPONSE))

    assert result.decision is InferenceLeaseDecision.ACQUIRED
    assert result.lease_id is not None
    assert result.snapshot.state is InferenceResourceState.BUSY
    assert result.snapshot.active_large_slots == 1
    assert await scheduler.release(result.lease_id) is True
    snapshot = await scheduler.snapshot()
    assert snapshot.state is InferenceResourceState.IDLE
    assert snapshot.active_large_slots == 0


async def test_large_llm_concurrency_limit_is_one() -> None:
    """Large LLM は同時1本に固定され、追加 user-facing は block せず defer する。"""
    scheduler = _scheduler(LocalInferenceResourcePolicy(enabled=True))
    first = await scheduler.acquire(_request(priority=InferenceWorkPriority.USER_FACING_RESPONSE))

    second = await scheduler.acquire(_request(priority=InferenceWorkPriority.USER_FACING_RESPONSE))

    assert first.decision is InferenceLeaseDecision.ACQUIRED
    assert second.decision is InferenceLeaseDecision.DEFER
    assert second.reason == "large LLM slot limit reached"


async def test_background_large_llm_defers_when_user_facing_is_active() -> None:
    """Background LLM work は busy large slot で待たずに defer する。"""
    scheduler = _scheduler()
    await scheduler.acquire(_request(priority=InferenceWorkPriority.USER_FACING_RESPONSE))

    result = await scheduler.acquire(
        _request(
            priority=InferenceWorkPriority.BACKGROUND,
            slot_kind=InferenceSlotKind.BACKGROUND_LLM,
            call_site=ModelCallSite.REFLECTION,
        )
    )

    assert result.decision is InferenceLeaseDecision.DEFER
    assert result.reason == "large LLM slot limit reached"


async def test_user_facing_defers_while_background_large_llm_is_running() -> None:
    """実行中 background LLM を安全停止できない間は user-facing も lease しない。"""
    scheduler = _scheduler()
    background = await scheduler.acquire(
        _request(
            priority=InferenceWorkPriority.BACKGROUND,
            slot_kind=InferenceSlotKind.BACKGROUND_LLM,
            call_site=ModelCallSite.REFLECTION,
        )
    )

    result = await scheduler.acquire(_request(priority=InferenceWorkPriority.USER_FACING_RESPONSE))

    assert background.lease_id is not None
    assert result.decision is InferenceLeaseDecision.DEFER
    assert result.reason == "large LLM slot limit reached"
    assert result.snapshot.active_large_slots == 1
    assert await scheduler.release(background.lease_id) is True


async def test_small_classifier_uses_separate_capacity() -> None:
    """Small classifier は large LLM slot と別枠で lease できる。"""
    scheduler = _scheduler()
    await scheduler.acquire(_request(priority=InferenceWorkPriority.USER_FACING_RESPONSE))

    result = await scheduler.acquire(
        _request(
            priority=InferenceWorkPriority.SAFETY_CRITICAL,
            slot_kind=InferenceSlotKind.SMALL_CLASSIFIER,
            call_site=ModelCallSite.USER_RESPONSE_HOT_PATH,
        )
    )

    assert result.decision is InferenceLeaseDecision.ACQUIRED
    assert result.snapshot.active_large_slots == 1
    assert result.snapshot.active_small_classifier_slots == 1


async def test_warming_defers_low_priority_but_allows_user_facing() -> None:
    """Warming 中は低優先度 work を defer し、user-facing は deterministic に許可する。"""
    scheduler = _scheduler()
    await scheduler.set_state(InferenceResourceState.WARMING)

    background = await scheduler.acquire(
        _request(priority=InferenceWorkPriority.BACKGROUND, call_site=ModelCallSite.REFLECTION)
    )
    user = await scheduler.acquire(_request(priority=InferenceWorkPriority.USER_FACING_RESPONSE))

    assert background.decision is InferenceLeaseDecision.DEFER
    assert background.reason == "local inference resource warming"
    assert user.decision is InferenceLeaseDecision.ACQUIRED


async def test_unavailable_maps_by_priority() -> None:
    """Unavailable 中は user-facing と proactive を policy どおり即時判定する。"""
    scheduler = _scheduler()
    await scheduler.set_state(InferenceResourceState.UNAVAILABLE)

    user = await scheduler.acquire(_request(priority=InferenceWorkPriority.USER_FACING_RESPONSE))
    proactive = await scheduler.acquire(
        _request(
            priority=InferenceWorkPriority.PROACTIVE,
            call_site=ModelCallSite.PROACTIVE,
        )
    )

    assert user.decision is InferenceLeaseDecision.DENIED
    assert proactive.decision is InferenceLeaseDecision.NO_SEND


async def test_proactive_large_llm_no_send_when_large_slot_is_busy() -> None:
    """Proactive generation は busy large slot で待たず no-send になる。"""
    scheduler = _scheduler()
    await scheduler.acquire(_request(priority=InferenceWorkPriority.USER_FACING_RESPONSE))

    result = await scheduler.acquire(
        _request(
            priority=InferenceWorkPriority.PROACTIVE,
            slot_kind=InferenceSlotKind.BACKGROUND_LLM,
            call_site=ModelCallSite.PROACTIVE,
        )
    )

    assert result.decision is InferenceLeaseDecision.NO_SEND
    assert result.reason == "large LLM slot limit reached"
