"""Interaction-policy candidate review and explicit promotion boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.interaction_policy import (
    ApprovedInteractionPolicy,
    InteractionPolicyCandidateId,
    InteractionPolicyDecisionKind,
)
from iris.contracts.review_candidates import (
    ReviewCandidateDetail,
    ReviewCandidateFilter,
    ReviewCandidateScope,
    ReviewCandidateStatus,
    ReviewCandidateSummary,
    ReviewCandidateType,
    ReviewDecisionKind,
    ReviewDecisionRequest,
    ReviewDecisionResult,
    ReviewInteractionPolicyCandidatePayload,
)
from iris.core.datetime_utils import now_utc
from iris.runtime.state.interaction_policy_candidates import (
    InteractionPolicyCandidateReviewId,
    InteractionPolicyCandidateReviewRecord,
    InteractionPolicyCandidateReviewStore,
    InteractionPolicyCandidateReviewUpdate,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime


class InteractionPolicyCandidateReviewError(RuntimeError):
    """Interaction policy review workflow の基底エラー。"""


class InteractionPolicyCandidateNotFoundError(InteractionPolicyCandidateReviewError):
    """未知の candidate id。"""


class InvalidInteractionPolicyCandidateReviewTransitionError(InteractionPolicyCandidateReviewError):
    """許可されない review lifecycle 遷移。"""


class InteractionPolicyCandidateReviewService:
    """Policy candidate を review boundary DTO へ変換して lifecycle 管理する。"""

    def __init__(
        self,
        store: InteractionPolicyCandidateReviewStore,
        *,
        now: Callable[[], datetime] = now_utc,
    ) -> None:
        """Review store と clock を注入する。"""
        self._store = store
        self._now = now

    async def list_candidates(
        self,
        query: ReviewCandidateFilter | None = None,
    ) -> tuple[ReviewCandidateSummary, ...]:
        """Interaction policy candidates だけを review summary として返す。

        Returns:
            Review summary DTO 列。
        """
        resolved = query or ReviewCandidateFilter(
            candidate_type=ReviewCandidateType.INTERACTION_POLICY
        )
        if resolved.candidate_type not in {None, ReviewCandidateType.INTERACTION_POLICY}:
            return ()
        records = await self._store.list_by_filter(resolved)
        return tuple(_summary_from_record(record) for record in records)

    async def read(self, candidate_id: InteractionPolicyCandidateReviewId) -> ReviewCandidateDetail:
        """Candidate detail を typed review DTO として返す。

        Returns:
            Typed candidate detail。

        """
        return _detail_from_record(await self._get_required(candidate_id))

    async def approve(
        self,
        candidate_id: InteractionPolicyCandidateReviewId,
        request: ReviewDecisionRequest | None = None,
    ) -> ReviewDecisionResult:
        """Pending candidate を明示承認する。

        Returns:
            Review decision result。
        """
        return await self._apply(
            candidate_id,
            ReviewDecisionKind.APPROVE,
            ReviewCandidateStatus.APPROVED,
            request,
        )

    async def reject(
        self,
        candidate_id: InteractionPolicyCandidateReviewId,
        request: ReviewDecisionRequest | None = None,
    ) -> ReviewDecisionResult:
        """Pending candidate を却下する。

        Returns:
            Review decision result。
        """
        return await self._apply(
            candidate_id,
            ReviewDecisionKind.REJECT,
            ReviewCandidateStatus.REJECTED,
            request,
        )

    async def discard(
        self,
        candidate_id: InteractionPolicyCandidateReviewId,
        request: ReviewDecisionRequest | None = None,
    ) -> ReviewDecisionResult:
        """Pending candidate を破棄する。

        Returns:
            Review decision result。
        """
        return await self._apply(
            candidate_id,
            ReviewDecisionKind.DISCARD,
            ReviewCandidateStatus.DISCARDED,
            request,
        )

    async def _get_required(
        self,
        candidate_id: InteractionPolicyCandidateReviewId,
    ) -> InteractionPolicyCandidateReviewRecord:
        record = await self._store.get(candidate_id)
        if record is None:
            raise InteractionPolicyCandidateNotFoundError(str(candidate_id))
        return record

    async def _apply(
        self,
        candidate_id: InteractionPolicyCandidateReviewId,
        decision: ReviewDecisionKind,
        target_status: ReviewCandidateStatus,
        request: ReviewDecisionRequest | None,
    ) -> ReviewDecisionResult:
        record = await self._get_required(candidate_id)
        if record.status is target_status:
            return ReviewDecisionResult(
                candidate=_detail_from_record(record),
                decision=decision,
                changed=False,
            )
        if record.status is not ReviewCandidateStatus.PENDING_REVIEW:
            message = f"cannot transition interaction policy candidate {candidate_id}"
            raise InvalidInteractionPolicyCandidateReviewTransitionError(message)
        resolved = request or ReviewDecisionRequest()
        now = self._now()
        updated = await self._store.update_review(
            candidate_id,
            InteractionPolicyCandidateReviewUpdate(
                status=target_status,
                updated_at=now,
                reviewed_at=now,
                reviewed_by=resolved.reviewed_by,
                review_reason=resolved.reason,
            ),
        )
        if updated is None:
            raise InteractionPolicyCandidateNotFoundError(str(candidate_id))
        return ReviewDecisionResult(
            candidate=_detail_from_record(updated),
            decision=decision,
            changed=True,
        )


@dataclass(frozen=True)
class InteractionPolicyPromotionResult:
    """承認済み policy の prompt integration 境界結果。"""

    record: InteractionPolicyCandidateReviewRecord
    policy: ApprovedInteractionPolicy | None
    promoted: bool
    reason: str | None = None


class ApprovedInteractionPolicyPromoter:
    """承認済み候補を scoped prompt policy DTO へ昇格する。"""

    def __init__(self, store: InteractionPolicyCandidateReviewStore) -> None:
        """Interaction policy review store を注入する。"""
        self._store = store

    async def promote(
        self,
        candidate_id: InteractionPolicyCandidateReviewId,
    ) -> InteractionPolicyPromotionResult:
        """Approved candidate だけを prompt integration 用 DTO に変換する。

        Global persona や canonical persona store は変更しない。suppressed candidate
        は review で approve されても安全境界として promotion しない。

        Returns:
            Prompt integration 用の promotion result。

        Raises:
            InteractionPolicyCandidateNotFoundError: candidate が存在しない場合。
        """
        record = await self._store.get(candidate_id)
        if record is None:
            raise InteractionPolicyCandidateNotFoundError(str(candidate_id))
        candidate = record.candidate
        if record.status is not ReviewCandidateStatus.APPROVED:
            return InteractionPolicyPromotionResult(
                record=record,
                policy=None,
                promoted=False,
                reason="candidate_not_approved",
            )
        if candidate.decision_kind is InteractionPolicyDecisionKind.SUPPRESSED:
            return InteractionPolicyPromotionResult(
                record=record,
                policy=None,
                promoted=False,
                reason="candidate_suppressed",
            )
        return InteractionPolicyPromotionResult(
            record=record,
            policy=ApprovedInteractionPolicy(
                candidate_id=InteractionPolicyCandidateId(str(candidate_id)),
                policy_kind=candidate.policy_kind,
                value=candidate.value,
                account_id=candidate.account_id,
                space_id=candidate.space_id,
                approved_at=record.updated_at,
            ),
            promoted=True,
        )


def _summary_from_record(record: InteractionPolicyCandidateReviewRecord) -> ReviewCandidateSummary:
    candidate = record.candidate
    return ReviewCandidateSummary(
        candidate_id=str(record.candidate_id),
        candidate_type=ReviewCandidateType.INTERACTION_POLICY,
        status=record.status,
        scope=ReviewCandidateScope(
            actor_id=candidate.actor_id,
            account_id=candidate.account_id,
            space_id=candidate.space_id,
        ),
        text_preview=f"{candidate.policy_kind.value}: {candidate.value}",
        confidence=candidate.confidence,
        reason=candidate.reason,
        created_at=record.created_at,
        updated_at=record.updated_at,
        metadata=record.metadata,
        candidate_metadata=candidate.metadata,
    )


def _detail_from_record(record: InteractionPolicyCandidateReviewRecord) -> ReviewCandidateDetail:
    candidate = record.candidate
    return ReviewCandidateDetail(
        candidate_id=str(record.candidate_id),
        candidate_type=ReviewCandidateType.INTERACTION_POLICY,
        status=record.status,
        scope=ReviewCandidateScope(
            actor_id=candidate.actor_id,
            account_id=candidate.account_id,
            space_id=candidate.space_id,
        ),
        interaction_policy_candidate=ReviewInteractionPolicyCandidatePayload(
            policy_kind=candidate.policy_kind,
            value=candidate.value,
            account_id=candidate.account_id,
            space_id=candidate.space_id,
            actor_id=candidate.actor_id,
            decision_kind=candidate.decision_kind,
            source_kinds=candidate.source_kinds,
            evidence_count=candidate.evidence_count,
            source_event_ids=candidate.source_event_ids,
            confidence=candidate.confidence,
            reason=candidate.reason,
            review_required=candidate.review_required,
            high_risk=candidate.high_risk,
            model_metadata=candidate.model_metadata,
            metadata=candidate.metadata,
        ),
        created_at=record.created_at,
        updated_at=record.updated_at,
        reviewed_at=record.reviewed_at,
        reviewed_by=record.reviewed_by,
        review_reason=record.review_reason,
        metadata=record.metadata,
        candidate_metadata=candidate.metadata,
    )
