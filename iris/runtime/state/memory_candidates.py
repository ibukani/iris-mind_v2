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
    from iris.core.ids import ActorId, ObservationId, SpaceId

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
    space_id: SpaceId | None = None
    source_observation_id: ObservationId | None = None
    metadata: ImmutableMetadata = field(default_factory=immutable_metadata)


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
        limit: int = 50,
    ) -> tuple[MemoryCandidateReviewRecord, ...]:
        """List pending review candidates in deterministic order.

        Returns:
            Pending records sorted by creation time and candidate id.
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
        limit: int = 50,
    ) -> tuple[MemoryCandidateReviewRecord, ...]:
        """List pending review candidates in deterministic order.

        Returns:
            Pending records sorted by creation time and candidate id.
        """
        with self._lock:
            records = [
                record
                for record in self._records.values()
                if record.status is MemoryCandidateReviewStatus.PENDING_REVIEW
                and (actor_id is None or record.actor_id == actor_id)
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
        with self._lock:
            record = self._records.get(candidate_id)
            if record is None:
                return None
            updated = replace(record, status=status, updated_at=updated_at)
            self._records[candidate_id] = updated
            return updated


@dataclass(frozen=True)
class MemoryCandidateReviewDecision:
    """Result of applying review-store admission policy to a candidate."""

    accepted: bool
    reason: str | None = None
