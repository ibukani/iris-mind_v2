"""BackgroundJobQueue policy / metrics tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from iris.runtime.learning.jobs import (
    BackgroundJobId,
    BackgroundJobKind,
    BackgroundJobRecord,
    BackgroundJobResourceProfile,
    DeferredLearningJobPayload,
)
from iris.runtime.learning.policy import (
    BackgroundJobBackpressureMode,
    BackgroundJobBackpressureReason,
    BackgroundJobEnqueueDecision,
    BackgroundJobKindPolicy,
    BackgroundJobQueuePolicy,
)
from iris.runtime.learning.queue import InMemoryBackgroundJobQueue

pytestmark = pytest.mark.anyio

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _job(
    key: str,
    *,
    kind: BackgroundJobKind = BackgroundJobKind.REFLECTION,
    created_at: datetime = _NOW,
) -> BackgroundJobRecord:
    return BackgroundJobRecord(
        job_id=BackgroundJobId(f"job-{key}"),
        kind=kind,
        payload=DeferredLearningJobPayload(reason="test"),
        not_before=_NOW,
        idempotency_key=key,
        created_at=created_at,
        updated_at=created_at,
    )


async def test_enqueue_with_policy_rejects_when_max_pending_reached() -> None:
    """kind別 pending 上限に達した enqueue は reject できる。"""
    queue = InMemoryBackgroundJobQueue()
    policy = BackgroundJobQueuePolicy(
        default_policy=BackgroundJobKindPolicy(
            max_pending_jobs=1,
            backpressure_mode=BackgroundJobBackpressureMode.REJECT,
        )
    )

    accepted = await queue.enqueue_with_policy(_job("first"), now=_NOW, policy=policy)
    rejected = await queue.enqueue_with_policy(_job("second"), now=_NOW, policy=policy)

    assert accepted.decision is BackgroundJobEnqueueDecision.ACCEPTED
    assert rejected.decision is BackgroundJobEnqueueDecision.REJECTED
    assert rejected.reason is BackgroundJobBackpressureReason.MAX_PENDING_JOBS


async def test_enqueue_with_policy_rejects_retry_storm() -> None:
    """failed_retryable backlog が saturated の場合は retry storm として reject する。"""
    queue = InMemoryBackgroundJobQueue()
    policy = BackgroundJobQueuePolicy(
        default_policy=BackgroundJobKindPolicy(
            max_pending_jobs=1,
            backpressure_mode=BackgroundJobBackpressureMode.REJECT,
        )
    )
    first = await queue.enqueue(_job("retry-first"))
    await queue.lease_due(_NOW, 1, 10.0)
    await queue.mark_retryable_failure(first.job_id, _NOW, "retry", _NOW)

    result = await queue.enqueue_with_policy(_job("retry-second"), now=_NOW, policy=policy)

    assert result.decision is BackgroundJobEnqueueDecision.REJECTED
    assert result.reason is BackgroundJobBackpressureReason.RETRY_STORM_PREVENTION


async def test_enqueue_backpressure_counts_combined_backlog() -> None:
    """Pending と failed_retryable の合計 backlog で上限判定する。"""
    queue = InMemoryBackgroundJobQueue()
    policy = BackgroundJobQueuePolicy(
        default_policy=BackgroundJobKindPolicy(
            max_pending_jobs=2,
            backpressure_mode=BackgroundJobBackpressureMode.REJECT,
        )
    )
    retryable = await queue.enqueue(_job("aaa-retryable"))
    await queue.lease_due(_NOW, 1, 10.0)
    await queue.mark_retryable_failure(retryable.job_id, _NOW, "retry", _NOW)
    await queue.enqueue(_job("zzz-pending"))

    result = await queue.enqueue_with_policy(_job("third"), now=_NOW, policy=policy)

    assert result.decision is BackgroundJobEnqueueDecision.REJECTED
    assert result.reason is BackgroundJobBackpressureReason.RETRY_STORM_PREVENTION


async def test_enqueue_backpressure_counts_expired_lease_as_backlog() -> None:
    """期限切れ lease は enqueue 上限判定でも backlog として扱う。"""
    queue = InMemoryBackgroundJobQueue()
    policy = BackgroundJobQueuePolicy(
        default_policy=BackgroundJobKindPolicy(
            max_pending_jobs=1,
            backpressure_mode=BackgroundJobBackpressureMode.REJECT,
        )
    )
    await queue.enqueue(_job("expired"))
    await queue.lease_due(_NOW, 1, 10.0)

    result = await queue.enqueue_with_policy(
        _job("after-expired"),
        now=_NOW + timedelta(seconds=10),
        policy=policy,
    )

    assert result.decision is BackgroundJobEnqueueDecision.REJECTED
    assert result.reason is BackgroundJobBackpressureReason.MAX_PENDING_JOBS


async def test_enqueue_with_policy_defers_idle_only_job_until_idle_available() -> None:
    """idle_only policy は idle でない enqueue を defer する。"""
    queue = InMemoryBackgroundJobQueue()
    policy = BackgroundJobQueuePolicy(
        default_policy=BackgroundJobKindPolicy(
            idle_only=True,
            defer_seconds_when_saturated=60.0,
        )
    )

    result = await queue.enqueue_with_policy(
        _job("idle"),
        now=_NOW,
        policy=policy,
        idle_available=False,
    )

    assert result.decision is BackgroundJobEnqueueDecision.DEFERRED
    assert result.reason is BackgroundJobBackpressureReason.IDLE_ONLY_NOT_AVAILABLE
    assert result.deferred_until == _NOW + timedelta(seconds=60)
    assert result.record is not None
    assert result.record.not_before == result.deferred_until


async def test_collect_metrics_reports_depth_oldest_age_and_per_kind_counts() -> None:
    """Queue metrics は全体と kind 別の状態件数を返す。"""
    queue = InMemoryBackgroundJobQueue()
    old_created = _NOW - timedelta(seconds=120)
    pending = await queue.enqueue(_job("pending", created_at=old_created))
    leased_source = await queue.enqueue(_job("leased", kind=BackgroundJobKind.MEMORY_EXTRACTION))
    leased = (await queue.lease_due(_NOW, 1, 30.0))[0]
    assert leased.job_id == pending.job_id
    await queue.mark_retryable_failure(leased_source.job_id, _NOW, "retry", _NOW)

    metrics = await queue.collect_metrics(_NOW)

    assert metrics.queue_depth == 1
    assert metrics.leased == 1
    assert metrics.failed_retryable == 1
    oldest_pending_age = metrics.oldest_pending_age_seconds
    assert oldest_pending_age is not None
    assert abs(oldest_pending_age) < 1e-9
    by_kind = {kind_metrics.kind: kind_metrics for kind_metrics in metrics.per_kind}
    assert by_kind[BackgroundJobKind.REFLECTION].leased == 1
    assert by_kind[BackgroundJobKind.MEMORY_EXTRACTION].failed_retryable == 1


async def test_per_kind_concurrency_ignores_expired_leases() -> None:
    """期限切れ lease は kind別 concurrency をブロックしない。"""
    queue = InMemoryBackgroundJobQueue()
    first = await queue.enqueue(_job("first"))
    await queue.enqueue(_job("second"))
    policy = BackgroundJobQueuePolicy(default_policy=BackgroundJobKindPolicy(concurrency_limit=1))

    leased_first = await queue.lease_due(_NOW, 1, 10.0, policy=policy)
    blocked = await queue.lease_due(_NOW, 1, 10.0, policy=policy)
    after_expiry = await queue.lease_due(_NOW + timedelta(seconds=10), 2, 10.0, policy=policy)

    assert leased_first[0].job_id == first.job_id
    assert blocked == ()
    assert after_expiry[0].job_id == first.job_id


async def test_lease_due_skips_idle_only_job_until_idle_available() -> None:
    """idle_only job は runtime lease 時にも idle でなければ実行しない。"""
    queue = InMemoryBackgroundJobQueue()
    idle_job = await queue.enqueue(
        _job("idle-runtime").model_copy(
            update={"resource_profile": BackgroundJobResourceProfile(idle_only=True)}
        )
    )

    blocked = await queue.lease_due(_NOW, 1, 10.0, idle_available=False)
    leased = await queue.lease_due(_NOW, 1, 10.0, idle_available=True)

    assert blocked == ()
    assert leased[0].job_id == idle_job.job_id


async def test_expired_lease_is_reported_as_queue_backlog() -> None:
    """期限切れ lease は active lease ではなく backlog として metrics に出す。"""
    queue = InMemoryBackgroundJobQueue()
    old_created = _NOW - timedelta(seconds=90)
    job = await queue.enqueue(_job("expired-metrics", created_at=old_created))
    await queue.lease_due(_NOW, 1, 10.0)

    metrics = await queue.collect_metrics(_NOW + timedelta(seconds=10))

    assert metrics.leased == 0
    assert metrics.queue_depth == 1
    oldest_pending_age = metrics.oldest_pending_age_seconds
    assert oldest_pending_age is not None
    assert abs(oldest_pending_age - 100.0) < 1e-9
    by_kind = {kind_metrics.kind: kind_metrics for kind_metrics in metrics.per_kind}
    assert by_kind[job.kind].pending == 1


async def test_enqueue_with_policy_treats_duplicate_job_id_as_existing() -> None:
    """job_id 重複は idempotency key が違っても既存 job として扱う。"""
    queue = InMemoryBackgroundJobQueue()
    first = await queue.enqueue_with_policy(
        _job("first"),
        now=_NOW,
        policy=BackgroundJobQueuePolicy(),
    )
    assert first.record is not None
    duplicate = _job("other").model_copy(update={"job_id": first.record.job_id})

    result = await queue.enqueue_with_policy(
        duplicate,
        now=_NOW,
        policy=BackgroundJobQueuePolicy(),
    )

    assert result.decision is BackgroundJobEnqueueDecision.EXISTING
    assert result.record == first.record


async def test_enqueue_with_policy_accept_mode_ignores_pressure_reason() -> None:
    """Accept mode は pressure reason があっても enqueue を許可する。"""
    queue = InMemoryBackgroundJobQueue()
    policy = BackgroundJobQueuePolicy(
        default_policy=BackgroundJobKindPolicy(
            max_pending_jobs=1,
            backpressure_mode=BackgroundJobBackpressureMode.ACCEPT,
        )
    )

    first = await queue.enqueue_with_policy(_job("accept-first"), now=_NOW, policy=policy)
    second = await queue.enqueue_with_policy(_job("accept-second"), now=_NOW, policy=policy)

    assert first.decision is BackgroundJobEnqueueDecision.ACCEPTED
    assert second.decision is BackgroundJobEnqueueDecision.ACCEPTED
    assert second.reason is None
    assert second.record is not None
