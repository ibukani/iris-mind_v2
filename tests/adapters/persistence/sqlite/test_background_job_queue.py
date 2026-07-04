"""SQLiteBackgroundJobQueue tests。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from iris.adapters.persistence.sqlite.stores.background_jobs import SQLiteBackgroundJobQueue
from iris.contracts.learning import RuntimeLearningEventKind
from iris.contracts.memory import MemoryKind
from iris.contracts.memory_candidates import (
    MemoryCandidateSensitivity,
    MemoryCandidateSource,
    MemoryRetentionPolicy,
)
from iris.contracts.model_policy import ModelCallDescriptor, ModelCallKind, ModelCallSite
from iris.contracts.observations import ObservationKind, UserFeedbackKind
from iris.core.ids import AccountId, ActorId, ObservationId, SessionId, SpaceId
from iris.runtime.learning.jobs import (
    BackgroundJobId,
    BackgroundJobKind,
    BackgroundJobRecord,
    BackgroundJobResourceProfile,
    BackgroundJobStatus,
    DeferredLearningJobPayload,
    MemoryBackgroundJobPayload,
    RuntimeLearningCandidateJobPayload,
)
from iris.runtime.learning.policy import (
    BackgroundJobBackpressureMode,
    BackgroundJobBackpressureReason,
    BackgroundJobEnqueueDecision,
    BackgroundJobKindPolicy,
    BackgroundJobQueuePolicy,
)
from iris.runtime.learning.queue import BackgroundJobQueueError

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.anyio
_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _queue(tmp_path: Path) -> SQLiteBackgroundJobQueue:
    return SQLiteBackgroundJobQueue(tmp_path / "state.sqlite3")


def _job(
    key: str,
    *,
    payload: object | None = None,
    max_attempts: int = 2,
) -> BackgroundJobRecord:
    resolved_payload = payload if payload is not None else DeferredLearningJobPayload(reason="test")
    if not isinstance(
        resolved_payload,
        (
            MemoryBackgroundJobPayload,
            RuntimeLearningCandidateJobPayload,
            DeferredLearningJobPayload,
        ),
    ):
        message = "test payload type is unsupported"
        raise TypeError(message)
    return BackgroundJobRecord(
        job_id=BackgroundJobId(f"job-{key}"),
        kind=BackgroundJobKind.REFLECTION,
        payload=resolved_payload,
        max_attempts=max_attempts,
        not_before=_NOW,
        idempotency_key=key,
        created_at=_NOW,
        updated_at=_NOW,
    )


async def test_enqueue_get_and_reopen_persist_pending_job(tmp_path: Path) -> None:
    """Pending job は reopen 後も取得できる。"""
    queue = _queue(tmp_path)
    job = await queue.enqueue(_job("pending"))
    queue.close()

    reopened = _queue(tmp_path)
    stored = await reopened.get(job.job_id)

    assert stored == job
    reopened.close()


async def test_enqueue_is_idempotent_by_key_and_job_id(tmp_path: Path) -> None:
    """idempotency_key と job_id の重複は既存 job を返す。"""
    queue = _queue(tmp_path)
    first = await queue.enqueue(_job("same-key"))
    same_key = await queue.enqueue(_job("same-key"))
    same_id = await queue.enqueue(
        _job("other-key").model_copy(update={"job_id": first.job_id}),
    )

    assert same_key == first
    assert same_id == first
    queue.close()


async def test_due_job_leases_once_until_expired(tmp_path: Path) -> None:
    """Lease 中 job は期限切れまで再 lease されない。"""
    queue = _queue(tmp_path)
    job = await queue.enqueue(_job("lease"))

    leased = await queue.lease_due(_NOW, 5, 10.0)
    second = await queue.lease_due(_NOW, 5, 10.0)
    expired = await queue.lease_due(_NOW + timedelta(seconds=10), 5, 10.0)

    assert leased[0].job_id == job.job_id
    assert leased[0].status is BackgroundJobStatus.LEASED
    assert second == ()
    assert expired[0].job_id == job.job_id
    queue.close()


async def test_retryable_failure_becomes_permanent_at_max_attempts(tmp_path: Path) -> None:
    """最大試行回数で恒久失敗へ遷移する。"""
    queue = _queue(tmp_path)
    job = await queue.enqueue(_job("retry", max_attempts=2))

    await queue.lease_due(_NOW, 1, 10.0)
    await queue.mark_retryable_failure(job.job_id, _NOW, "first", _NOW)
    first_failure = await queue.get(job.job_id)
    await queue.lease_due(_NOW, 1, 10.0)
    await queue.mark_retryable_failure(job.job_id, _NOW, "second", _NOW)
    second_failure = await queue.get(job.job_id)

    assert first_failure.status is BackgroundJobStatus.FAILED_RETRYABLE
    assert first_failure.attempts == 1
    assert second_failure.status is BackgroundJobStatus.FAILED_PERMANENT
    assert second_failure.attempts == 2
    queue.close()


async def test_success_and_permanent_failure_are_terminal(tmp_path: Path) -> None:
    """成功と恒久失敗は due lease 対象から外れる。"""
    queue = _queue(tmp_path)
    succeeded = await queue.enqueue(_job("ok"))
    failed = await queue.enqueue(_job("bad"))

    await queue.mark_succeeded(succeeded.job_id, _NOW)
    await queue.mark_permanent_failure(failed.job_id, _NOW, "no worker")

    assert (await queue.get(succeeded.job_id)).status is BackgroundJobStatus.SUCCEEDED
    assert (await queue.get(failed.job_id)).status is BackgroundJobStatus.FAILED_PERMANENT
    assert await queue.lease_due(_NOW, 5, 10.0) == ()
    queue.close()


@pytest.mark.parametrize(
    "payload",
    [
        DeferredLearningJobPayload(source_observation_id=ObservationId("obs-1"), reason="later"),
        MemoryBackgroundJobPayload(
            text="ユーザーは短い返答を好む。",
            memory_kind=MemoryKind.PREFERENCE,
            source=MemoryCandidateSource.IMPLICIT_CONVERSATION,
            reason="test",
            retention_policy=MemoryRetentionPolicy.REVIEW_REQUIRED,
            sensitivity=MemoryCandidateSensitivity.NORMAL,
            review_required=True,
            salience=0.6,
            confidence=0.7,
            actor_id=ActorId("actor-1"),
            space_id=SpaceId("space-1"),
            source_observation_id=ObservationId("obs-1"),
        ),
        RuntimeLearningCandidateJobPayload(
            event_kind=RuntimeLearningEventKind.USER_FEEDBACK,
            route="runtime",
            observation_kind=ObservationKind.USER_FEEDBACK,
            input_text="今後は短く返して",
            output_text=None,
            feedback_kind=UserFeedbackKind.STYLE_PREFERENCE,
            actor_id=ActorId("actor-1"),
            account_id=AccountId("account-1"),
            space_id=SpaceId("space-1"),
            session_id=SessionId("session-1"),
            source_observation_id=ObservationId("obs-1"),
            occurred_at=_NOW,
        ),
    ],
)
async def test_payload_round_trips(tmp_path: Path, payload: object) -> None:
    """対応 payload union を SQLite 経由で lossless に復元する。"""
    queue = _queue(tmp_path)
    job = await queue.enqueue(_job("payload", payload=payload))

    stored = await queue.get(job.job_id)

    assert stored.payload == payload
    queue.close()


async def test_unknown_job_raises_queue_error(tmp_path: Path) -> None:
    """未知 job_id は明示エラーにする。"""
    queue = _queue(tmp_path)

    with pytest.raises(BackgroundJobQueueError):
        await queue.get(BackgroundJobId("missing"))

    queue.close()


async def test_enqueue_with_policy_rejects_when_max_pending_reached(tmp_path: Path) -> None:
    """SQLite queue でも kind別 pending 上限に達した enqueue は reject する。"""
    queue = _queue(tmp_path)
    policy = BackgroundJobQueuePolicy(
        default_policy=BackgroundJobKindPolicy(
            max_pending_jobs=1,
            backpressure_mode=BackgroundJobBackpressureMode.REJECT,
        )
    )

    accepted = await queue.enqueue_with_policy(_job("policy-first"), now=_NOW, policy=policy)
    rejected = await queue.enqueue_with_policy(_job("policy-second"), now=_NOW, policy=policy)

    assert accepted.decision is BackgroundJobEnqueueDecision.ACCEPTED
    assert rejected.decision is BackgroundJobEnqueueDecision.REJECTED
    assert rejected.reason is BackgroundJobBackpressureReason.MAX_PENDING_JOBS
    queue.close()


async def test_enqueue_with_policy_rejects_retry_storm(tmp_path: Path) -> None:
    """SQLite queue でも failed_retryable backlog は retry storm として reject する。"""
    queue = _queue(tmp_path)
    policy = BackgroundJobQueuePolicy(
        default_policy=BackgroundJobKindPolicy(
            max_pending_jobs=1,
            backpressure_mode=BackgroundJobBackpressureMode.REJECT,
        )
    )
    first = await queue.enqueue(_job("retry-storm-first"))
    await queue.lease_due(_NOW, 1, 10.0)
    await queue.mark_retryable_failure(first.job_id, _NOW, "retry", _NOW)

    result = await queue.enqueue_with_policy(
        _job("retry-storm-second"),
        now=_NOW,
        policy=policy,
    )

    assert result.decision is BackgroundJobEnqueueDecision.REJECTED
    assert result.reason is BackgroundJobBackpressureReason.RETRY_STORM_PREVENTION
    queue.close()


async def test_enqueue_backpressure_counts_combined_backlog(tmp_path: Path) -> None:
    """SQLite queue でも combined backlog で enqueue 上限判定する。"""
    queue = _queue(tmp_path)
    policy = BackgroundJobQueuePolicy(
        default_policy=BackgroundJobKindPolicy(
            max_pending_jobs=2,
            backpressure_mode=BackgroundJobBackpressureMode.REJECT,
        )
    )
    retryable = await queue.enqueue(_job("sqlite-aaa-retryable"))
    await queue.lease_due(_NOW, 1, 10.0)
    await queue.mark_retryable_failure(retryable.job_id, _NOW, "retry", _NOW)
    await queue.enqueue(_job("sqlite-zzz-pending"))

    result = await queue.enqueue_with_policy(_job("sqlite-third"), now=_NOW, policy=policy)

    assert result.decision is BackgroundJobEnqueueDecision.REJECTED
    assert result.reason is BackgroundJobBackpressureReason.RETRY_STORM_PREVENTION
    queue.close()


async def test_enqueue_backpressure_counts_expired_lease_as_backlog(tmp_path: Path) -> None:
    """SQLite queue でも期限切れ lease を enqueue backlog として扱う。"""
    queue = _queue(tmp_path)
    policy = BackgroundJobQueuePolicy(
        default_policy=BackgroundJobKindPolicy(
            max_pending_jobs=1,
            backpressure_mode=BackgroundJobBackpressureMode.REJECT,
        )
    )
    await queue.enqueue(_job("sqlite-expired-backpressure"))
    await queue.lease_due(_NOW, 1, 10.0)

    result = await queue.enqueue_with_policy(
        _job("sqlite-after-expired"),
        now=_NOW + timedelta(seconds=10),
        policy=policy,
    )

    assert result.decision is BackgroundJobEnqueueDecision.REJECTED
    assert result.reason is BackgroundJobBackpressureReason.MAX_PENDING_JOBS
    queue.close()


async def test_collect_metrics_reports_per_kind_counts(tmp_path: Path) -> None:
    """SQLite queue metrics は kind 別状態件数を返す。"""
    queue = _queue(tmp_path)
    first = await queue.enqueue(_job("metrics-first"))
    await queue.enqueue(
        _job("metrics-second").model_copy(update={"kind": BackgroundJobKind.MEMORY_EXTRACTION})
    )
    leased = (await queue.lease_due(_NOW, 1, 30.0))[0]
    assert leased.job_id == first.job_id

    metrics = await queue.collect_metrics(_NOW)

    by_kind = {kind_metrics.kind: kind_metrics for kind_metrics in metrics.per_kind}
    assert metrics.queue_depth == 1
    assert metrics.leased == 1
    assert by_kind[BackgroundJobKind.REFLECTION].leased == 1
    assert by_kind[BackgroundJobKind.MEMORY_EXTRACTION].pending == 1
    queue.close()


async def test_policy_lease_ignores_expired_leases(tmp_path: Path) -> None:
    """SQLite queue の kind別 concurrency は期限切れ lease を active 扱いしない。"""
    queue = _queue(tmp_path)
    first = await queue.enqueue(_job("expired-first"))
    await queue.enqueue(_job("expired-second"))
    policy = BackgroundJobQueuePolicy(default_policy=BackgroundJobKindPolicy(concurrency_limit=1))

    leased_first = await queue.lease_due(_NOW, 1, 10.0, policy=policy)
    blocked = await queue.lease_due(_NOW, 1, 10.0, policy=policy)
    after_expiry = await queue.lease_due(_NOW + timedelta(seconds=10), 2, 10.0, policy=policy)

    assert leased_first[0].job_id == first.job_id
    assert blocked == ()
    assert after_expiry[0].job_id == first.job_id
    queue.close()


async def test_resource_profile_and_defer_reason_roundtrip(tmp_path: Path) -> None:
    """Resource profile と defer reason は SQLite で永続化される。"""
    queue = _queue(tmp_path)
    policy = BackgroundJobQueuePolicy(
        default_policy=BackgroundJobKindPolicy(idle_only=True, defer_seconds_when_saturated=45.0)
    )
    descriptor = ModelCallDescriptor(
        call_kind=ModelCallKind.BACKGROUND_LLM,
        call_site=ModelCallSite.MEMORY_EXTRACTION,
    )
    profile = BackgroundJobResourceProfile(
        uses_llm=True,
        idle_only=True,
        model_call_descriptor=descriptor,
    )

    result = await queue.enqueue_with_policy(
        _job("profile").model_copy(update={"resource_profile": profile}),
        now=_NOW,
        policy=policy,
        idle_available=False,
    )
    assert result.record is not None
    queue.close()

    reopened = _queue(tmp_path)
    stored = await reopened.get(result.record.job_id)

    assert stored.defer_reason == BackgroundJobBackpressureReason.IDLE_ONLY_NOT_AVAILABLE.value
    assert stored.not_before == _NOW + timedelta(seconds=45)
    assert stored.resource_profile.uses_llm is True
    assert stored.resource_profile.idle_only is True
    assert stored.resource_profile.model_call_descriptor == descriptor
    reopened.close()


async def test_enqueue_with_policy_accept_mode_ignores_pressure_reason(tmp_path: Path) -> None:
    """SQLite queue の Accept mode は pressure reason があっても保存する。"""
    queue = _queue(tmp_path)
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
    assert await queue.get(second.record.job_id) == second.record
    queue.close()


async def test_lease_due_skips_idle_only_job_until_idle_available(tmp_path: Path) -> None:
    """SQLite queue でも idle_only job は idle でなければ lease しない。"""
    queue = _queue(tmp_path)
    idle_job = await queue.enqueue(
        _job("sqlite-idle-runtime").model_copy(
            update={"resource_profile": BackgroundJobResourceProfile(idle_only=True)}
        )
    )

    blocked = await queue.lease_due(_NOW, 1, 10.0, idle_available=False)
    leased = await queue.lease_due(_NOW, 1, 10.0, idle_available=True)

    assert blocked == ()
    assert leased[0].job_id == idle_job.job_id
    queue.close()


async def test_expired_lease_is_reported_as_queue_backlog(tmp_path: Path) -> None:
    """SQLite metrics でも期限切れ lease は backlog として観測できる。"""
    queue = _queue(tmp_path)
    created_at = _NOW - timedelta(seconds=90)
    job = await queue.enqueue(
        _job("sqlite-expired-metrics").model_copy(
            update={"created_at": created_at, "updated_at": created_at}
        )
    )
    await queue.lease_due(_NOW, 1, 10.0)

    metrics = await queue.collect_metrics(_NOW + timedelta(seconds=10))

    assert metrics.leased == 0
    assert metrics.queue_depth == 1
    oldest_pending_age = metrics.oldest_pending_age_seconds
    assert oldest_pending_age is not None
    assert abs(oldest_pending_age - 100.0) < 1e-9
    by_kind = {kind_metrics.kind: kind_metrics for kind_metrics in metrics.per_kind}
    assert by_kind[job.kind].pending == 1
    queue.close()


async def test_mark_cancelled_persists_cancelled_metrics(tmp_path: Path) -> None:
    """SQLite queue は policy cancellation を cancelled metrics に反映する。"""
    queue = _queue(tmp_path)
    job = await queue.enqueue(_job("cancelled"))
    await queue.lease_due(_NOW, 1, 10.0)

    await queue.mark_cancelled(job.job_id, _NOW, "scheduler no-send")

    stored = await queue.get(job.job_id)
    metrics = await queue.collect_metrics(_NOW)
    assert stored.status is BackgroundJobStatus.CANCELLED
    assert stored.last_error == "scheduler no-send"
    assert metrics.cancelled == 1
    assert metrics.failed_permanent == 0
    assert metrics.queue_depth == 0
    queue.close()
