"""配送後イベントから明示的メモリジョブを登録する保守的フック。"""

from __future__ import annotations

from hashlib import sha256
from typing import TYPE_CHECKING, Protocol

from iris.contracts.actions import ActionStatus
from iris.runtime.learning.jobs import (
    BackgroundJobId,
    BackgroundJobKind,
    BackgroundJobRecord,
    MemoryBackgroundJobPayload,
)

if TYPE_CHECKING:
    from datetime import datetime

    from iris.contracts.learning import LearningEvent
    from iris.runtime.learning.queue import InMemoryBackgroundJobQueue


class ExplicitMemoryPayloadResolver(Protocol):
    """配送文脈から推測せず明示 payload を解決する境界。"""

    def resolve(self, event: LearningEvent) -> MemoryBackgroundJobPayload | None:
        """十分な明示文脈がなければ None を返す。"""
        ...


class EnqueueExplicitMemoryLearningHook:
    """成功配送かつ明示 payload がある場合だけジョブを登録する。"""

    def __init__(
        self,
        queue: InMemoryBackgroundJobQueue,
        resolver: ExplicitMemoryPayloadResolver,
        *,
        max_attempts: int = 3,
    ) -> None:
        """キュー、明示入力 resolver、再試行上限を注入する。"""
        self._queue = queue
        self._resolver = resolver
        self._max_attempts = max_attempts

    async def after_action_result(self, event: LearningEvent) -> None:
        """成功以外や不十分な文脈を安全に無視する。"""
        if event.result.status is not ActionStatus.SUCCEEDED:
            return
        payload = self._resolver.resolve(event)
        if payload is None:
            return
        key = _job_key(event, payload)
        await self._queue.enqueue(_new_job(key, payload, event.reported_at, self._max_attempts))


def _job_key(event: LearningEvent, payload: MemoryBackgroundJobPayload) -> str:
    material = "|".join(
        (
            str(event.result.action_id),
            str(event.result.correlation_id),
            payload.text,
            payload.source.value,
        )
    )
    return sha256(material.encode()).hexdigest()


def _new_job(
    key: str,
    payload: MemoryBackgroundJobPayload,
    now: datetime,
    max_attempts: int,
) -> BackgroundJobRecord:
    return BackgroundJobRecord(
        job_id=BackgroundJobId(f"memory-{key[:24]}"),
        kind=BackgroundJobKind.MEMORY_CONSOLIDATION,
        payload=payload,
        max_attempts=max_attempts,
        not_before=now,
        idempotency_key=key,
        created_at=now,
        updated_at=now,
    )
