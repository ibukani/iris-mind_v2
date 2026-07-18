"""Process-local review store for interaction-policy candidates."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from threading import RLock
from typing import TYPE_CHECKING, NewType, Protocol

from iris.contracts.review_candidates import (
    ReviewCandidateFilter,
    ReviewCandidateStatus,
    ReviewCandidateType,
)
from iris.core.metadata import immutable_metadata

if TYPE_CHECKING:
    from datetime import datetime

    from iris.contracts.interaction_policy import InteractionPolicyCandidate
    from iris.contracts.metadata import ImmutableMetadata
    from iris.core.ids import AccountId, ActorId, SpaceId

InteractionPolicyCandidateReviewId = NewType("InteractionPolicyCandidateReviewId", str)


@dataclass(frozen=True)
class InteractionPolicyCandidateReviewRecord:
    """Review boundary に保持する interaction policy candidate。"""

    candidate_id: InteractionPolicyCandidateReviewId
    candidate: InteractionPolicyCandidate
    created_at: datetime
    updated_at: datetime
    idempotency_key: str
    status: ReviewCandidateStatus = ReviewCandidateStatus.PENDING_REVIEW
    actor_id: ActorId | None = None
    account_id: AccountId | None = None
    space_id: SpaceId | None = None
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    review_reason: str | None = None
    metadata: ImmutableMetadata = field(default_factory=immutable_metadata)


@dataclass(frozen=True)
class InteractionPolicyCandidateReviewUpdate:
    """Review lifecycle metadata の更新 patch。"""

    status: ReviewCandidateStatus
    updated_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    review_reason: str | None = None


class InteractionPolicyCandidateReviewStore(Protocol):
    """Interaction policy review candidate の typed store。"""

    async def add(
        self,
        record: InteractionPolicyCandidateReviewRecord,
    ) -> InteractionPolicyCandidateReviewRecord:
        """候補を冪等に追加する。"""
        ...

    def add_nowait(
        self,
        record: InteractionPolicyCandidateReviewRecord,
    ) -> InteractionPolicyCandidateReviewRecord:
        """同期 worker から候補を追加する。"""
        ...

    async def get(
        self,
        candidate_id: InteractionPolicyCandidateReviewId,
    ) -> InteractionPolicyCandidateReviewRecord | None:
        """候補を一件取得する。"""
        ...

    async def list_by_filter(
        self,
        query: ReviewCandidateFilter,
    ) -> tuple[InteractionPolicyCandidateReviewRecord, ...]:
        """Scope / lifecycle filter で候補を列挙する。"""
        ...

    async def update_review(
        self,
        candidate_id: InteractionPolicyCandidateReviewId,
        update: InteractionPolicyCandidateReviewUpdate,
    ) -> InteractionPolicyCandidateReviewRecord | None:
        """Review lifecycle を更新する。"""
        ...


class InMemoryInteractionPolicyCandidateReviewStore:
    """冪等な process-local interaction policy review store。"""

    def __init__(self) -> None:
        """空の process-local store を作る。"""
        self._records: dict[
            InteractionPolicyCandidateReviewId,
            InteractionPolicyCandidateReviewRecord,
        ] = {}
        self._idempotency_keys: dict[str, InteractionPolicyCandidateReviewId] = {}
        self._lock = RLock()

    async def add(
        self,
        record: InteractionPolicyCandidateReviewRecord,
    ) -> InteractionPolicyCandidateReviewRecord:
        """候補を冪等に追加する。

        Returns:
            既存または追加した候補。
        """
        return self.add_nowait(record)

    def add_nowait(
        self,
        record: InteractionPolicyCandidateReviewRecord,
    ) -> InteractionPolicyCandidateReviewRecord:
        """同期 worker から候補を冪等に追加する。

        Returns:
            既存または追加した候補。
        """
        with self._lock:
            existing = self._records.get(record.candidate_id)
            if existing is not None:
                return existing
            existing_id = self._idempotency_keys.get(record.idempotency_key)
            if existing_id is not None:
                return self._records[existing_id]
            self._records[record.candidate_id] = record
            self._idempotency_keys[record.idempotency_key] = record.candidate_id
            return record

    async def get(
        self,
        candidate_id: InteractionPolicyCandidateReviewId,
    ) -> InteractionPolicyCandidateReviewRecord | None:
        """Candidate id に対応する候補を返す。

        Returns:
            Candidate、または未登録の場合は ``None``。
        """
        with self._lock:
            return self._records.get(candidate_id)

    async def list_by_filter(
        self,
        query: ReviewCandidateFilter,
    ) -> tuple[InteractionPolicyCandidateReviewRecord, ...]:
        """Filter に一致する候補を deterministic order で返す。

        Returns:
            Filter に一致する候補列。
        """
        with self._lock:
            records = tuple(
                sorted(
                    (record for record in self._records.values() if _matches_filter(record, query)),
                    key=_record_sort_key,
                )
            )
            return records[: query.limit]

    async def update_review(
        self,
        candidate_id: InteractionPolicyCandidateReviewId,
        update: InteractionPolicyCandidateReviewUpdate,
    ) -> InteractionPolicyCandidateReviewRecord | None:
        """Review lifecycle を更新する。

        Returns:
            更新後の候補、または未登録の場合は ``None``。
        """
        with self._lock:
            record = self._records.get(candidate_id)
            if record is None:
                return None
            updated = replace(
                record,
                status=update.status,
                updated_at=update.updated_at,
                reviewed_at=update.reviewed_at,
                reviewed_by=update.reviewed_by,
                review_reason=update.review_reason,
            )
            self._records[candidate_id] = updated
            return updated


def _matches_filter(
    record: InteractionPolicyCandidateReviewRecord,
    query: ReviewCandidateFilter,
) -> bool:
    return (
        (query.status is None or record.status is query.status)
        and (
            query.candidate_type is None
            or query.candidate_type is ReviewCandidateType.INTERACTION_POLICY
        )
        and (query.actor_id is None or record.actor_id == query.actor_id)
        and (query.account_id is None or record.account_id == query.account_id)
        and (query.space_id is None or record.space_id == query.space_id)
    )


def _record_sort_key(
    record: InteractionPolicyCandidateReviewRecord,
) -> tuple[object, str]:
    return record.created_at, str(record.candidate_id)
