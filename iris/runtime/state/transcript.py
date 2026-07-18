"""Transcript persistence store ports and process-local null implementation。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from iris.contracts.ordering import (
    OrderingConflict,
    OrderingConflictReason,
    OrderingDecision,
    OrderingDecisionKind,
    RuntimeOrderingKey,
    RuntimeOrderingKeyKind,
)
from iris.contracts.transcript import (
    TranscriptCleanupRequest,
    TranscriptCleanupResult,
    TranscriptPruneResult,
)

if TYPE_CHECKING:
    from datetime import datetime

    from iris.contracts.transcript import TranscriptQuery, TranscriptRecord


class TranscriptStore(Protocol):
    """確定済み transcript record の永続化境界。"""

    async def append(self, records: tuple[TranscriptRecord, ...]) -> None:
        """Transcript record を追記する。"""
        ...

    async def query(self, query: TranscriptQuery) -> tuple[TranscriptRecord, ...]:
        """境界付き query で transcript record を取得する。"""
        ...

    async def prune_expired(self, now: datetime) -> TranscriptPruneResult:
        """保持期限を過ぎた transcript record を削除する。"""
        ...


class TranscriptCleanupStore(Protocol):
    """Transcript cleanup の durable mutation 境界。"""

    async def cleanup(self, request: TranscriptCleanupRequest) -> TranscriptCleanupResult:
        """Scoped cleanupをidempotentに実行する。"""
        ...


class NullTranscriptStore:
    """Transcript persistence を無効化する no-op store。"""

    def __init__(self) -> None:
        """No-op store を初期化する。"""
        self._ignored_record_count = 0

    async def append(self, records: tuple[TranscriptRecord, ...]) -> None:
        """Record を保存せずに破棄する。"""
        self._ignored_record_count += len(records)

    async def query(self, query: TranscriptQuery) -> tuple[TranscriptRecord, ...]:
        """保存無効時は常に空集合を返す。

        Returns:
            空の transcript record 集合。
        """
        if query.limit <= 0 and self._ignored_record_count == 0:
            return ()
        return ()

    async def prune_expired(self, now: datetime) -> TranscriptPruneResult:
        """保存無効時は削除対象なしを返す。

        Returns:
            削除件数 0。
        """
        if now.tzinfo is None and self._ignored_record_count == 0:
            return TranscriptPruneResult(deleted_count=0)
        return TranscriptPruneResult(deleted_count=0)

    @staticmethod
    async def cleanup(request: TranscriptCleanupRequest) -> TranscriptCleanupResult:
        """保存無効時はdefer decisionを返し、mutationしない。

        Returns:
            Durable backend unavailable を示す defer result。
        """
        _ = request
        return TranscriptCleanupResult(
            operation_id=request.operation_id,
            dry_run=request.dry_run,
            target_count=0,
            eligible_count=0,
            deleted_count=0,
            excluded_count=0,
            decision=_disabled_cleanup_decision(request),
        )


def _disabled_cleanup_decision(request: TranscriptCleanupRequest) -> OrderingDecision:
    return OrderingDecision(
        key=RuntimeOrderingKey(
            kind=RuntimeOrderingKeyKind.TRANSCRIPT,
            actor_id=request.scope.actor_id,
            account_id=request.scope.account_id,
            space_id=request.scope.space_id,
            session_id=request.scope.session_id,
        ),
        decision=OrderingDecisionKind.DEFER,
        conflict=OrderingConflict(
            reason=OrderingConflictReason.BACKEND_UNAVAILABLE,
            expected_version="durable_transcript_store",
            observed_version="disabled",
        ),
    )
