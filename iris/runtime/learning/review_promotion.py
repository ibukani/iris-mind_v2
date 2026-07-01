"""承認済み implicit review candidate から durable memory への promotion。"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING

from iris.cognitive.memory.candidates import (
    MemoryCandidateSensitivity,
    MemoryCandidateSource,
    MemoryRetentionPolicy,
)
from iris.cognitive.memory.safety import (
    contains_credential_like_content,
    contains_sensitive_profile_content,
    is_unsafe_preferred_name_memory_text,
)
from iris.contracts.memory import MemoryId, MemoryRecord
from iris.core.datetime_utils import now_utc
from iris.core.metadata import immutable_metadata
from iris.runtime.state.memory_candidates import (
    MemoryCandidateReviewStatus,
    MemoryCandidateReviewUpdate,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from iris.cognitive.memory.candidates import MemoryCandidate
    from iris.contracts.memory import MutableMemoryStore
    from iris.runtime.state.memory_candidates import (
        MemoryCandidateReviewId,
        MemoryCandidateReviewRecord,
        MemoryCandidateReviewStore,
    )


@dataclass(frozen=True)
class ApprovedImplicitMemoryPromotionPolicy:
    """承認済み implicit candidate の durable write 前 policy。"""

    min_confidence: float = 0.35
    max_text_length: int = 5000
    allow_sensitive_candidates: bool = False

    def accept(self, candidate: MemoryCandidate) -> bool:
        """承認済み implicit candidate を promotion してよいか判定する。

        Returns:
            Promotion を許可する場合は True。
        """
        text = candidate.text.strip()
        return (
            self._content_is_valid(text, candidate)
            and self._provenance_is_valid(candidate)
            and self._safety_is_valid(text, candidate)
        )

    def _content_is_valid(self, text: str, candidate: MemoryCandidate) -> bool:
        return (
            bool(text)
            and len(text) <= self.max_text_length
            and candidate.confidence >= self.min_confidence
        )

    @staticmethod
    def _provenance_is_valid(candidate: MemoryCandidate) -> bool:
        return (
            candidate.source is MemoryCandidateSource.IMPLICIT_CONVERSATION
            and candidate.retention_policy is MemoryRetentionPolicy.REVIEW_REQUIRED
            and candidate.review_required
        )

    def _safety_is_valid(self, text: str, candidate: MemoryCandidate) -> bool:
        rejected = (
            contains_credential_like_content(text)
            or candidate.sensitivity is MemoryCandidateSensitivity.SECRET_LIKE
            or is_unsafe_preferred_name_memory_text(text)
            or (contains_sensitive_profile_content(text) and not self.allow_sensitive_candidates)
        )
        accepted_sensitivity = {
            MemoryCandidateSensitivity.NORMAL,
            MemoryCandidateSensitivity.PERSONAL,
        }
        if self.allow_sensitive_candidates:
            accepted_sensitivity.add(MemoryCandidateSensitivity.SENSITIVE)
        return not rejected and candidate.sensitivity in accepted_sensitivity


@dataclass(frozen=True)
class MemoryCandidatePromotionResult:
    """承認済み memory candidate の promotion 結果。"""

    record: MemoryCandidateReviewRecord
    memory: MemoryRecord | None
    promoted: bool
    reason: str | None = None


class MemoryCandidatePromotionError(RuntimeError):
    """Memory candidate promotion workflow の基底エラー。"""


class MemoryCandidatePromotionNotFoundError(MemoryCandidatePromotionError):
    """Promotion 対象 candidate が存在しない場合のエラー。"""


class ApprovedMemoryCandidatePromoter:
    """明示承認済み implicit candidate を canonical MemoryStore へ昇格する。"""

    def __init__(
        self,
        review_store: MemoryCandidateReviewStore,
        memory_store: MutableMemoryStore,
        *,
        policy: ApprovedImplicitMemoryPromotionPolicy | None = None,
        now: Callable[[], datetime] = now_utc,
    ) -> None:
        """Review store、canonical memory store、policy、clock を注入する。"""
        self._review_store = review_store
        self._memory_store = memory_store
        self._policy = policy or ApprovedImplicitMemoryPromotionPolicy()
        self._now = now

    async def promote(
        self,
        candidate_id: MemoryCandidateReviewId,
    ) -> MemoryCandidatePromotionResult:
        """承認済み candidate を policy が許可する場合だけ promotion する。

        Returns:
            書き込み結果、または promotion しなかった理由。

        Raises:
            MemoryCandidatePromotionNotFoundError: candidate id が未知の場合。
        """
        record = await self._review_store.get(candidate_id)
        if record is None:
            raise MemoryCandidatePromotionNotFoundError(str(candidate_id))

        if record.status is not MemoryCandidateReviewStatus.APPROVED:
            result = MemoryCandidatePromotionResult(
                record=record,
                memory=None,
                promoted=False,
                reason="candidate_not_approved",
            )
        elif record.promoted_memory_id is not None:
            result = self._already_promoted_result(record)
        elif not self._policy.accept(record.candidate):
            result = MemoryCandidatePromotionResult(
                record=record,
                memory=None,
                promoted=False,
                reason="candidate_rejected_by_promotion_policy",
            )
        else:
            result = await self._promote_approved_candidate(record, candidate_id)
        return result

    def _already_promoted_result(
        self,
        record: MemoryCandidateReviewRecord,
    ) -> MemoryCandidatePromotionResult:
        memory = self._memory_store.get(MemoryId(record.promoted_memory_id or ""))
        reason = "promoted_memory_missing" if memory is None else "already_promoted"
        return MemoryCandidatePromotionResult(
            record=record,
            memory=memory,
            promoted=False,
            reason=reason,
        )

    async def _promote_approved_candidate(
        self,
        record: MemoryCandidateReviewRecord,
        candidate_id: MemoryCandidateReviewId,
    ) -> MemoryCandidatePromotionResult:
        now = self._now()
        memory_id = _promoted_memory_id(record)
        memory = self._memory_store.update(_memory_record(record, memory_id, now))
        # 現在は in-memory review store 前提の二段階更新。将来 review store を
        # durable 化する段階では MemoryStore 更新と review metadata 更新の
        # transaction/compensation policy を同じ境界で定義する。
        updated = await self._review_store.update_review(
            candidate_id,
            MemoryCandidateReviewUpdate(
                status=MemoryCandidateReviewStatus.APPROVED,
                updated_at=now,
                promoted_memory_id=str(memory.id),
            ),
        )
        return MemoryCandidatePromotionResult(
            record=updated or record,
            memory=memory,
            promoted=True,
            reason=None,
        )


def _promoted_memory_id(record: MemoryCandidateReviewRecord) -> MemoryId:
    material = f"{record.candidate_id}|{record.idempotency_key}"
    digest = sha256(material.encode()).hexdigest()
    return MemoryId(f"approved-implicit-{digest[:24]}")


def _memory_record(
    record: MemoryCandidateReviewRecord,
    memory_id: MemoryId,
    now: datetime,
) -> MemoryRecord:
    candidate = record.candidate
    return MemoryRecord(
        id=memory_id,
        text=candidate.text.strip(),
        actor_id=candidate.actor_id,
        space_id=candidate.space_id,
        salience=candidate.salience,
        kind=candidate.kind,
        confidence=candidate.confidence,
        source_observation_id=candidate.source_observation_id,
        created_at=now,
        updated_at=now,
        metadata=immutable_metadata(
            {
                "candidate_source": candidate.source.value,
                "original_retention_policy": candidate.retention_policy.value,
                "retention_policy": MemoryRetentionPolicy.DURABLE.value,
                "sensitivity": candidate.sensitivity.value,
                "review_required_original": "true" if candidate.review_required else "false",
                "review_required": "false",
                "review_status": MemoryCandidateReviewStatus.APPROVED.value,
                "review_candidate_id": str(record.candidate_id),
                "reviewed_by": record.reviewed_by or "",
                "review_reason": record.review_reason or "",
                "reason": candidate.reason or "",
                "confidence": str(candidate.confidence),
                "source_observation_id": str(candidate.source_observation_id or ""),
            }
        ),
    )
