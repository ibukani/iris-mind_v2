"""Implicit memory candidate の明示 review workflow。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.core.datetime_utils import now_utc
from iris.runtime.state.memory_candidates import (
    MemoryCandidateReviewStatus,
    MemoryCandidateReviewUpdate,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from iris.core.ids import AccountId, ActorId, SpaceId
    from iris.runtime.state.memory_candidates import (
        MemoryCandidateReviewId,
        MemoryCandidateReviewRecord,
        MemoryCandidateReviewStore,
    )


class MemoryCandidateReviewError(RuntimeError):
    """Memory candidate review workflow の基底エラー。"""


class MemoryCandidateNotFoundError(MemoryCandidateReviewError):
    """Review candidate が存在しない場合のエラー。"""


class InvalidMemoryCandidateReviewTransitionError(MemoryCandidateReviewError):
    """許可されない review lifecycle 遷移のエラー。"""


@dataclass(frozen=True)
class MemoryCandidateReviewResult:
    """Review lifecycle decision の適用結果。"""

    record: MemoryCandidateReviewRecord
    changed: bool


class MemoryCandidateReviewService:
    """Implicit memory candidate を明示的に承認・却下する service。"""

    def __init__(
        self,
        store: MemoryCandidateReviewStore,
        *,
        now: Callable[[], datetime] = now_utc,
    ) -> None:
        """Review store と clock を明示注入する。"""
        self._store = store
        self._now = now

    async def list_pending(
        self,
        *,
        actor_id: ActorId | None = None,
        account_id: AccountId | None = None,
        space_id: SpaceId | None = None,
        limit: int = 50,
    ) -> tuple[MemoryCandidateReviewRecord, ...]:
        """明示 review 待ちの candidate を返す。

        Returns:
            Pending review candidate の一覧。
        """
        return await self._store.list_pending(
            actor_id=actor_id,
            account_id=account_id,
            space_id=space_id,
            limit=limit,
        )

    async def list_by_status(
        self,
        status: MemoryCandidateReviewStatus,
        *,
        actor_id: ActorId | None = None,
        account_id: AccountId | None = None,
        space_id: SpaceId | None = None,
        limit: int = 50,
    ) -> tuple[MemoryCandidateReviewRecord, ...]:
        """指定された review lifecycle status の candidate を返す。

        Returns:
            指定 status に一致する review candidate の一覧。
        """
        return await self._store.list_by_status(
            status,
            actor_id=actor_id,
            account_id=account_id,
            space_id=space_id,
            limit=limit,
        )

    async def approve(
        self,
        candidate_id: MemoryCandidateReviewId,
        *,
        reviewed_by: str | None = None,
        reason: str | None = None,
    ) -> MemoryCandidateReviewResult:
        """Pending candidate を promotion 可能な状態として承認する。

        Returns:
            更新後、または冪等 no-op の review result。
        """
        return await self._apply(
            candidate_id,
            MemoryCandidateReviewStatus.APPROVED,
            reviewed_by=reviewed_by,
            reason=reason,
        )

    async def reject(
        self,
        candidate_id: MemoryCandidateReviewId,
        *,
        reviewed_by: str | None = None,
        reason: str | None = None,
    ) -> MemoryCandidateReviewResult:
        """Pending candidate を却下し、promotion 対象から外す。

        Returns:
            更新後、または冪等 no-op の review result。
        """
        return await self._apply(
            candidate_id,
            MemoryCandidateReviewStatus.REJECTED,
            reviewed_by=reviewed_by,
            reason=reason,
        )

    async def discard(
        self,
        candidate_id: MemoryCandidateReviewId,
        *,
        reviewed_by: str | None = None,
        reason: str | None = None,
    ) -> MemoryCandidateReviewResult:
        """Pending candidate を破棄し、promotion 対象から外す。

        Returns:
            更新後、または冪等 no-op の review result。
        """
        return await self._apply(
            candidate_id,
            MemoryCandidateReviewStatus.DISCARDED,
            reviewed_by=reviewed_by,
            reason=reason,
        )

    async def _apply(
        self,
        candidate_id: MemoryCandidateReviewId,
        target_status: MemoryCandidateReviewStatus,
        *,
        reviewed_by: str | None,
        reason: str | None,
    ) -> MemoryCandidateReviewResult:
        record = await self._store.get(candidate_id)
        if record is None:
            raise MemoryCandidateNotFoundError(str(candidate_id))
        if record.status is target_status:
            return MemoryCandidateReviewResult(record=record, changed=False)
        if record.status is not MemoryCandidateReviewStatus.PENDING_REVIEW:
            message = (
                f"cannot transition memory candidate {candidate_id} "
                f"from {record.status.value} to {target_status.value}"
            )
            raise InvalidMemoryCandidateReviewTransitionError(message)
        now = self._now()
        updated = await self._store.update_review(
            candidate_id,
            MemoryCandidateReviewUpdate(
                status=target_status,
                updated_at=now,
                reviewed_at=now,
                reviewed_by=reviewed_by,
                review_reason=reason,
            ),
        )
        if updated is None:
            raise MemoryCandidateNotFoundError(str(candidate_id))
        return MemoryCandidateReviewResult(record=updated, changed=True)
