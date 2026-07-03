"""学習候補 review service boundary の型付き契約。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from iris.contracts.memory import MemoryKind
from iris.contracts.memory_candidates import (
    MemoryCandidateSensitivity,
    MemoryCandidateSource,
    MemoryRetentionPolicy,
)
from iris.contracts.metadata import ImmutableMetadata
from iris.core.ids import AccountId, ActorId, ObservationId, SpaceId


class ReviewCandidateType(StrEnum):
    """Review boundary で扱う学習候補の種別。"""

    MEMORY = "memory"
    SHARED_EPISODIC_MEMORY = "shared_episodic_memory"
    PERSONA_PATCH = "persona_patch"
    RELATIONSHIP = "relationship"
    INTERNAL_STATE = "internal_state"
    CONSOLIDATION = "consolidation"


class ReviewCandidateStatus(StrEnum):
    """候補の review lifecycle 状態。"""

    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    DISCARDED = "discarded"


class ReviewDecisionKind(StrEnum):
    """Review service が受け付ける明示 decision。"""

    APPROVE = "approve"
    REJECT = "reject"
    DISCARD = "discard"


class ReviewCandidateScope(BaseModel):
    """候補の actor / account / space 境界。"""

    model_config = ConfigDict(frozen=True)

    actor_id: ActorId | None = None
    account_id: AccountId | None = None
    space_id: SpaceId | None = None


class ReviewCandidateFilter(BaseModel):
    """Review candidate の list 境界で使う filter。"""

    model_config = ConfigDict(frozen=True)

    status: ReviewCandidateStatus | None = ReviewCandidateStatus.PENDING_REVIEW
    candidate_type: ReviewCandidateType | None = None
    actor_id: ActorId | None = None
    account_id: AccountId | None = None
    space_id: SpaceId | None = None
    limit: int = Field(default=50, ge=1)


class ReviewDecisionRequest(BaseModel):
    """approve / reject / discard の reviewer metadata。"""

    model_config = ConfigDict(frozen=True)

    reviewed_by: str | None = None
    reason: str | None = None


class ReviewMemoryCandidatePayload(BaseModel):
    """Memory candidate review detail の typed payload。"""

    model_config = ConfigDict(frozen=True)

    text: str
    kind: MemoryKind
    salience: float
    confidence: float
    source: MemoryCandidateSource
    reason: str | None = None
    retention_policy: MemoryRetentionPolicy
    sensitivity: MemoryCandidateSensitivity
    review_required: bool
    actor_id: ActorId | None = None
    space_id: SpaceId | None = None
    source_observation_id: ObservationId | None = None
    metadata: ImmutableMetadata = Field(default_factory=dict)


class ReviewCandidateSummary(BaseModel):
    """List API 用の review candidate summary。"""

    model_config = ConfigDict(frozen=True)

    candidate_id: str
    candidate_type: ReviewCandidateType
    status: ReviewCandidateStatus
    scope: ReviewCandidateScope
    source_observation_id: ObservationId | None = None
    text_preview: str
    confidence: float
    reason: str | None = None
    created_at: datetime
    updated_at: datetime
    metadata: ImmutableMetadata = Field(default_factory=dict)
    candidate_metadata: ImmutableMetadata = Field(default_factory=dict)


class ReviewCandidateDetail(BaseModel):
    """Read API 用の review candidate detail。"""

    model_config = ConfigDict(frozen=True)

    candidate_id: str
    candidate_type: ReviewCandidateType
    status: ReviewCandidateStatus
    scope: ReviewCandidateScope
    source_observation_id: ObservationId | None = None
    memory_candidate: ReviewMemoryCandidatePayload | None = None
    created_at: datetime
    updated_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    review_reason: str | None = None
    promoted_memory_id: str | None = None
    metadata: ImmutableMetadata = Field(default_factory=dict)
    candidate_metadata: ImmutableMetadata = Field(default_factory=dict)


class ReviewDecisionResult(BaseModel):
    """Review decision 適用結果。"""

    model_config = ConfigDict(frozen=True)

    candidate: ReviewCandidateDetail
    decision: ReviewDecisionKind
    changed: bool
