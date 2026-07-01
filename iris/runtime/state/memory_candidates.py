"""Process-local review store for implicit memory candidates."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from threading import RLock
from typing import TYPE_CHECKING, NewType, Protocol

from iris.core.metadata import immutable_metadata

if TYPE_CHECKING:
    from datetime import datetime

    from iris.cognitive.memory.candidates import MemoryCandidate
    from iris.contracts.metadata import ImmutableMetadata
    from iris.core.ids import AccountId, ActorId, ObservationId, SpaceId

MemoryCandidateReviewId = NewType("MemoryCandidateReviewId", str)


class MemoryCandidateReviewStatus(StrEnum):
    """Review lifecycle for implicit memory candidates."""

    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    DISCARDED = "discarded"


@dataclass(frozen=True)
class MemoryCandidateReviewRecord:
    """A memory candidate awaiting explicit review/promotion."""

    candidate_id: MemoryCandidateReviewId
    candidate: MemoryCandidate
    created_at: datetime
    updated_at: datetime
    idempotency_key: str
    status: MemoryCandidateReviewStatus = MemoryCandidateReviewStatus.PENDING_REVIEW
    actor_id: ActorId | None = None
    account_id: AccountId | None = None
    space_id: SpaceId | None = None
    source_observation_id: ObservationId | None = None
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    review_reason: str | None = None
    promoted_memory_id: str | None = None
    metadata: ImmutableMetadata = field(default_factory=immutable_metadata)


@dataclass(frozen=True)
class MemoryCandidateReviewUpdate:
    """Review lifecycle と review/promotion metadata の更新 patch。"""

    status: MemoryCandidateReviewStatus
    updated_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    review_reason: str | None = None
    promoted_memory_id: str | None = None


class MemoryCandidateReviewStore(Protocol):
    """Store for implicit candidates that must not be written to MemoryStore directly."""

    async def add(self, record: MemoryCandidateReviewRecord) -> MemoryCandidateReviewRecord:
        """Add a candidate idempotently."""
        ...

    def add_nowait(self, record: MemoryCandidateReviewRecord) -> MemoryCandidateReviewRecord:
        """Add a candidate from synchronous background workers."""
        ...

    async def get(
        self,
        candidate_id: MemoryCandidateReviewId,
    ) -> MemoryCandidateReviewRecord | None:
        """Return one candidate by id."""
        ...

    async def list_pending(
        self,
        *,
        actor_id: ActorId | None = None,
        account_id: AccountId | None = None,
        space_id: SpaceId | None = None,
        limit: int = 50,
    ) -> tuple[MemoryCandidateReviewRecord, ...]:
        """List pending review candidates in deterministic order.

        Returns:
            Pending records sorted by creation time and candidate id.
        """
        ...

    async def list_by_status(
        self,
        status: MemoryCandidateReviewStatus,
        *,
        actor_id: ActorId | None = None,
        account_id: AccountId | None = None,
        space_id: SpaceId | None = None,
        limit: int = 50,
    ) -> tuple[MemoryCandidateReviewRecord, ...]:
        """指定 status の review candidate を決定的順序で返す。

        Returns:
            作成時刻と candidate id で整列済みの matching record。
        """
        ...

    async def update_status(
        self,
        candidate_id: MemoryCandidateReviewId,
        status: MemoryCandidateReviewStatus,
        *,
        updated_at: datetime,
    ) -> MemoryCandidateReviewRecord | None:
        """Update review status for a candidate.

        Returns:
            Updated record, or None when the candidate does not exist.
        """
        ...

    async def update_review(
        self,
        candidate_id: MemoryCandidateReviewId,
        update: MemoryCandidateReviewUpdate,
    ) -> MemoryCandidateReviewRecord | None:
        """Review lifecycle と review/promotion metadata を更新する。

        Returns:
            更新後の record。candidate が存在しない場合は None。
        """
        ...


class InMemoryMemoryCandidateReviewStore:
    """In-memory candidate review store with idempotency-key deduplication."""

    def __init__(self) -> None:
        """Initialize an empty process-local review store."""
        self._records: dict[MemoryCandidateReviewId, MemoryCandidateReviewRecord] = {}
        self._idempotency_keys: dict[str, MemoryCandidateReviewId] = {}
        self._lock = RLock()

    async def add(self, record: MemoryCandidateReviewRecord) -> MemoryCandidateReviewRecord:
        """Add a candidate idempotently.

        Returns:
            Existing or newly stored candidate record.
        """
        return self.add_nowait(record)

    def add_nowait(self, record: MemoryCandidateReviewRecord) -> MemoryCandidateReviewRecord:
        """Add a candidate from synchronous background workers.

        Returns:
            Existing or newly stored candidate record.
        """
        with self._lock:
            existing_record = self._records.get(record.candidate_id)
            if existing_record is not None:
                return existing_record
            existing_id = self._idempotency_keys.get(record.idempotency_key)
            if existing_id is not None:
                return self._records[existing_id]
            self._records[record.candidate_id] = record
            self._idempotency_keys[record.idempotency_key] = record.candidate_id
            return record

    async def get(
        self,
        candidate_id: MemoryCandidateReviewId,
    ) -> MemoryCandidateReviewRecord | None:
        """Return one candidate by id."""
        with self._lock:
            return self._records.get(candidate_id)

    async def list_pending(
        self,
        *,
        actor_id: ActorId | None = None,
        account_id: AccountId | None = None,
        space_id: SpaceId | None = None,
        limit: int = 50,
    ) -> tuple[MemoryCandidateReviewRecord, ...]:
        """List pending review candidates in deterministic order.

        Returns:
            Pending records sorted by creation time and candidate id.
        """
        return await self.list_by_status(
            MemoryCandidateReviewStatus.PENDING_REVIEW,
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
        """指定 status の review candidate を決定的順序で返す。

        Returns:
            作成時刻と candidate id で整列済みの matching record。
        """
        _validate_positive_limit(limit)
        with self._lock:
            records = [
                record
                for record in self._records.values()
                if record.status is status
                and (actor_id is None or record.actor_id == actor_id)
                and (account_id is None or record.account_id == account_id)
                and (space_id is None or record.space_id == space_id)
            ]
            records.sort(key=lambda record: (record.created_at, str(record.candidate_id)))
            return tuple(records[:limit])

    async def update_status(
        self,
        candidate_id: MemoryCandidateReviewId,
        status: MemoryCandidateReviewStatus,
        *,
        updated_at: datetime,
    ) -> MemoryCandidateReviewRecord | None:
        """Update review status for a candidate.

        Returns:
            Updated record, or None when the candidate does not exist.
        """
        return await self.update_review(
            candidate_id,
            MemoryCandidateReviewUpdate(status=status, updated_at=updated_at),
        )

    async def update_review(
        self,
        candidate_id: MemoryCandidateReviewId,
        update: MemoryCandidateReviewUpdate,
    ) -> MemoryCandidateReviewRecord | None:
        """Review lifecycle と review/promotion metadata を更新する。

        Returns:
            更新後の record。candidate が存在しない場合は None。
        """
        with self._lock:
            record = self._records.get(candidate_id)
            if record is None:
                return None
            updated = replace(
                record,
                status=update.status,
                updated_at=update.updated_at,
                reviewed_at=update.reviewed_at
                if update.reviewed_at is not None
                else record.reviewed_at,
                reviewed_by=update.reviewed_by
                if update.reviewed_by is not None
                else record.reviewed_by,
                review_reason=(
                    update.review_reason
                    if update.review_reason is not None
                    else record.review_reason
                ),
                promoted_memory_id=(
                    update.promoted_memory_id
                    if update.promoted_memory_id is not None
                    else record.promoted_memory_id
                ),
            )
            self._records[candidate_id] = updated
            return updated


@dataclass(frozen=True)
class MemoryCandidateReviewDecision:
    """Result of applying review-store admission policy to a candidate."""

    accepted: bool
    reason: str | None = None


def _validate_positive_limit(limit: int) -> None:
    """Review candidate list の取得件数を検証する。

    Raises:
        ValueError: 取得件数が 1 未満の場合。
    """
    if limit < 1:
        message = "memory candidate review list limit must be >= 1"
        raise ValueError(message)
