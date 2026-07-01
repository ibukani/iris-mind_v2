"""SQLiteBackgroundJobQueue tests。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from iris.adapters.persistence.sqlite.stores.background_jobs import SQLiteBackgroundJobQueue
from iris.cognitive.memory.candidates import (
    MemoryCandidateSensitivity,
    MemoryCandidateSource,
    MemoryRetentionPolicy,
)
from iris.contracts.learning import RuntimeLearningEventKind
from iris.contracts.memory import MemoryKind
from iris.contracts.observations import ObservationKind, UserFeedbackKind
from iris.core.ids import AccountId, ActorId, ObservationId, SessionId, SpaceId
from iris.runtime.learning.jobs import (
    BackgroundJobId,
    BackgroundJobKind,
    BackgroundJobRecord,
    BackgroundJobStatus,
    DeferredLearningJobPayload,
    MemoryBackgroundJobPayload,
    RuntimeLearningCandidateJobPayload,
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
