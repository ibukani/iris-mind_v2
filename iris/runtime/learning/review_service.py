"""Learning candidate の明示 review service boundary。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.contracts.memory_consolidation import MemoryConsolidationDecisionKind
from iris.contracts.review_candidates import (
    ReviewCandidateDetail,
    ReviewCandidateFilter,
    ReviewCandidateScope,
    ReviewCandidateStatus,
    ReviewCandidateSummary,
    ReviewCandidateType,
    ReviewConsolidationCandidatePayload,
    ReviewDecisionKind,
    ReviewDecisionRequest,
    ReviewDecisionResult,
    ReviewMemoryCandidatePayload,
)
from iris.core.datetime_utils import now_utc
from iris.core.metadata import immutable_metadata
from iris.runtime.state.memory_candidates import (
    MemoryCandidateReviewStatus,
    MemoryCandidateReviewUpdate,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from datetime import datetime

    from iris.contracts.metadata import ImmutableMetadata
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


class MemoryCandidateReviewService:
    """学習候補を内部 store record から分離して review する service。"""

    def __init__(
        self,
        store: MemoryCandidateReviewStore,
        *,
        now: Callable[[], datetime] = now_utc,
    ) -> None:
        """Review store と clock を明示注入する。"""
        self._store = store
        self._now = now

    async def list_candidates(
        self,
        query: ReviewCandidateFilter | None = None,
    ) -> tuple[ReviewCandidateSummary, ...]:
        """Review candidate を filter 付きで列挙する。

        Returns:
            内部 store record を公開しない summary DTO。
        """
        resolved_query = query or ReviewCandidateFilter()
        records = await self._store.list_by_filter(resolved_query)
        return tuple(_summary_from_record(record) for record in records)

    async def read(self, candidate_id: MemoryCandidateReviewId) -> ReviewCandidateDetail:
        """Review candidate を service boundary 経由で読む。

        Returns:
            内部 store record を公開しない detail DTO。

        """
        record = await self._get_required(candidate_id)
        return _detail_from_record(record)

    async def approve(
        self,
        candidate_id: MemoryCandidateReviewId,
        request: ReviewDecisionRequest | None = None,
    ) -> ReviewDecisionResult:
        """Pending candidate を promotion 可能な状態として承認する。

        Returns:
            更新後、または冪等 no-op の review decision result。
        """
        return await self._apply(
            candidate_id,
            ReviewDecisionKind.APPROVE,
            MemoryCandidateReviewStatus.APPROVED,
            request=request,
        )

    async def reject(
        self,
        candidate_id: MemoryCandidateReviewId,
        request: ReviewDecisionRequest | None = None,
    ) -> ReviewDecisionResult:
        """Pending candidate を却下し、promotion 対象から外す。

        Returns:
            更新後、または冪等 no-op の review decision result。
        """
        return await self._apply(
            candidate_id,
            ReviewDecisionKind.REJECT,
            MemoryCandidateReviewStatus.REJECTED,
            request=request,
        )

    async def discard(
        self,
        candidate_id: MemoryCandidateReviewId,
        request: ReviewDecisionRequest | None = None,
    ) -> ReviewDecisionResult:
        """Pending candidate を破棄し、promotion 対象から外す。

        Returns:
            更新後、または冪等 no-op の review decision result。
        """
        return await self._apply(
            candidate_id,
            ReviewDecisionKind.DISCARD,
            MemoryCandidateReviewStatus.DISCARDED,
            request=request,
        )

    async def _get_required(
        self,
        candidate_id: MemoryCandidateReviewId,
    ) -> MemoryCandidateReviewRecord:
        record = await self._store.get(candidate_id)
        if record is None:
            raise MemoryCandidateNotFoundError(str(candidate_id))
        return record

    async def _apply(
        self,
        candidate_id: MemoryCandidateReviewId,
        decision: ReviewDecisionKind,
        target_status: MemoryCandidateReviewStatus,
        *,
        request: ReviewDecisionRequest | None,
    ) -> ReviewDecisionResult:
        record = await self._get_required(candidate_id)
        if record.status is target_status:
            return ReviewDecisionResult(
                candidate=_detail_from_record(record),
                decision=decision,
                changed=False,
            )
        if record.status is not MemoryCandidateReviewStatus.PENDING_REVIEW:
            message = (
                f"cannot transition memory candidate {candidate_id} "
                f"from {record.status.value} to {target_status.value}"
            )
            raise InvalidMemoryCandidateReviewTransitionError(message)
        now = self._now()
        decision_request = request or ReviewDecisionRequest()
        updated = await self._store.update_review(
            candidate_id,
            MemoryCandidateReviewUpdate(
                status=target_status,
                updated_at=now,
                reviewed_at=now,
                reviewed_by=decision_request.reviewed_by,
                review_reason=decision_request.reason,
            ),
        )
        if updated is None:
            raise MemoryCandidateNotFoundError(str(candidate_id))
        return ReviewDecisionResult(
            candidate=_detail_from_record(updated),
            decision=decision,
            changed=True,
        )


def _summary_from_record(record: MemoryCandidateReviewRecord) -> ReviewCandidateSummary:
    candidate = record.candidate
    return ReviewCandidateSummary(
        candidate_id=str(record.candidate_id),
        candidate_type=record.candidate_type,
        status=ReviewCandidateStatus(record.status.value),
        scope=_scope_from_record(record),
        source_observation_id=record.source_observation_id,
        text_preview=_preview(candidate.text),
        confidence=candidate.confidence,
        reason=candidate.reason,
        created_at=record.created_at,
        updated_at=record.updated_at,
        metadata=record.metadata,
        candidate_metadata=candidate.metadata,
    )


def _detail_from_record(record: MemoryCandidateReviewRecord) -> ReviewCandidateDetail:
    is_consolidation = record.candidate_type is ReviewCandidateType.CONSOLIDATION
    return ReviewCandidateDetail(
        candidate_id=str(record.candidate_id),
        candidate_type=record.candidate_type,
        status=ReviewCandidateStatus(record.status.value),
        scope=_scope_from_record(record),
        source_observation_id=record.source_observation_id,
        memory_candidate=None if is_consolidation else _memory_payload(record),
        consolidation_candidate=(_consolidation_payload(record) if is_consolidation else None),
        created_at=record.created_at,
        updated_at=record.updated_at,
        reviewed_at=record.reviewed_at,
        reviewed_by=record.reviewed_by,
        review_reason=record.review_reason,
        promoted_memory_id=record.promoted_memory_id,
        metadata=record.metadata,
        candidate_metadata=record.candidate.metadata,
    )


def _memory_payload(record: MemoryCandidateReviewRecord) -> ReviewMemoryCandidatePayload:
    candidate = record.candidate
    return ReviewMemoryCandidatePayload(
        text=candidate.text,
        kind=candidate.kind,
        salience=candidate.salience,
        confidence=candidate.confidence,
        source=candidate.source,
        reason=candidate.reason,
        retention_policy=candidate.retention_policy,
        sensitivity=candidate.sensitivity,
        review_required=candidate.review_required,
        actor_id=candidate.actor_id,
        space_id=candidate.space_id,
        source_observation_id=candidate.source_observation_id,
        source_event_ids=_split_candidate_ids(candidate.metadata.get("source_event_ids", "")),
        model_metadata=_model_metadata(candidate.metadata),
        metadata=candidate.metadata,
    )


def _consolidation_payload(
    record: MemoryCandidateReviewRecord,
) -> ReviewConsolidationCandidatePayload:
    """Consolidation record を typed review payload に変換する。

    Returns:
        review service boundary 用の typed payload。
    """
    candidate = record.candidate
    metadata = candidate.metadata
    return ReviewConsolidationCandidatePayload(
        text=candidate.text,
        kind=candidate.kind,
        salience=candidate.salience,
        confidence=candidate.confidence,
        source=candidate.source,
        reason=candidate.reason or metadata.get("consolidation_reason", "consolidation review"),
        retention_policy=candidate.retention_policy,
        sensitivity=candidate.sensitivity,
        review_required=candidate.review_required,
        decision_kind=MemoryConsolidationDecisionKind(metadata["consolidation_decision"]),
        source_candidate_ids=_split_candidate_ids(metadata.get("source_candidate_ids", "")),
        supersedes_candidate_ids=_split_candidate_ids(metadata.get("supersedes_candidate_ids", "")),
        actor_id=candidate.actor_id,
        account_id=record.account_id,
        space_id=candidate.space_id,
        source_observation_id=candidate.source_observation_id,
        metadata=metadata,
    )


def _split_candidate_ids(value: str) -> tuple[str, ...]:
    """保存済みの区切り文字列を candidate ID 列へ戻す。

    Returns:
        空要素を除いた candidate ID tuple。
    """
    return tuple(item for item in value.split("|") if item)


def _model_metadata(metadata: Mapping[str, str]) -> ImmutableMetadata:
    """Candidate metadata から model provenance だけを抽出する。

    Returns:
        model_* key の immutable metadata。
    """
    return immutable_metadata(
        {key: value for key, value in metadata.items() if key.startswith("model_")}
    )


def _scope_from_record(record: MemoryCandidateReviewRecord) -> ReviewCandidateScope:
    return ReviewCandidateScope(
        actor_id=record.actor_id,
        account_id=record.account_id,
        space_id=record.space_id,
    )


def _preview(text: str, *, max_length: int = 120) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[: max_length - 1]}…"
