"""学習候補 review service boundary の型付き契約。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from iris.contracts.interaction_policy import (
    InteractionPolicyDecisionKind,
    InteractionPolicyKind,
    InteractionPolicySourceKind,
)
from iris.contracts.memory import MemoryKind
from iris.contracts.memory_candidates import (
    MemoryCandidateSensitivity,
    MemoryCandidateSource,
    MemoryRetentionPolicy,
)
from iris.contracts.memory_consolidation import MemoryConsolidationDecisionKind
from iris.contracts.metadata import ImmutableMetadata
from iris.contracts.shared_episodic_memory import (
    SharedEpisodicAdmissionPolicy,
    SharedEpisodicAdmissionRisk,
    SharedEpisodicMemoryKind,
    SharedEpisodicRetrievalMetadata,
    SharedEpisodicSourceEventRef,
)
from iris.core.ids import AccountId, ActorId, ObservationId, SpaceId


class ReviewCandidateType(StrEnum):
    """Review boundary で扱う学習候補の種別。"""

    MEMORY = "memory"
    SHARED_EPISODIC_MEMORY = "shared_episodic_memory"
    PERSONA_PATCH = "persona_patch"
    RELATIONSHIP = "relationship"
    INTERNAL_STATE = "internal_state"
    CONSOLIDATION = "consolidation"
    INTERACTION_POLICY = "interaction_policy"


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
    source_event_ids: tuple[str, ...] = ()
    model_metadata: ImmutableMetadata = Field(default_factory=dict)
    metadata: ImmutableMetadata = Field(default_factory=dict)


class ReviewInteractionPolicyCandidatePayload(BaseModel):
    """Interaction policy candidate review detail の typed payload。"""

    model_config = ConfigDict(frozen=True)

    policy_kind: InteractionPolicyKind
    value: str = Field(min_length=1, max_length=160)
    account_id: AccountId
    space_id: SpaceId | None = None
    actor_id: ActorId | None = None
    decision_kind: InteractionPolicyDecisionKind
    source_kinds: tuple[InteractionPolicySourceKind, ...] = Field(min_length=1)
    evidence_count: int = Field(ge=1)
    source_event_ids: tuple[str, ...] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)
    review_required: bool
    high_risk: bool = False
    model_metadata: ImmutableMetadata = Field(default_factory=dict)
    metadata: ImmutableMetadata = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_candidate_contract(self) -> ReviewInteractionPolicyCandidatePayload:
        """Review payload でも candidate の review-only boundary を検証する。

        Returns:
            検証済み review payload。

        Raises:
            ValueError: evidence または review-only boundary が不正な場合。
        """
        if not self.value.strip() or not self.reason.strip():
            message = "interaction policy payload text fields must not be blank"
            raise ValueError(message)
        if self.evidence_count != len(self.source_event_ids):
            message = "interaction policy payload evidence_count must match source_event_ids"
            raise ValueError(message)
        if any(not event_id.strip() for event_id in self.source_event_ids):
            message = "interaction policy payload source_event_ids must not be blank"
            raise ValueError(message)
        if not self.review_required:
            message = "interaction policy payload must remain review_required"
            raise ValueError(message)
        if self.decision_kind is InteractionPolicyDecisionKind.SUPPRESSED and not self.high_risk:
            message = "suppressed interaction policy payload must be high_risk"
            raise ValueError(message)
        return self


class ReviewConsolidationCandidatePayload(BaseModel):
    """Memory consolidation candidate review detail の typed payload。"""

    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1)
    kind: MemoryKind
    salience: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    source: MemoryCandidateSource
    reason: str = Field(min_length=1)
    retention_policy: MemoryRetentionPolicy
    sensitivity: MemoryCandidateSensitivity
    review_required: bool
    decision_kind: MemoryConsolidationDecisionKind
    source_candidate_ids: tuple[str, ...] = Field(min_length=1)
    supersedes_candidate_ids: tuple[str, ...] = ()
    actor_id: ActorId | None = None
    account_id: AccountId | None = None
    space_id: SpaceId | None = None
    source_observation_id: ObservationId | None = None
    metadata: ImmutableMetadata = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_review_only_contract(self) -> ReviewConsolidationCandidatePayload:
        """Consolidation candidate を review-only に固定する。

        Returns:
            検証済みの consolidation review payload。

        Raises:
            ValueError: source、retention、review、supersession の整合性が不正な場合。
        """
        if self.source is not MemoryCandidateSource.CONSOLIDATION:
            message = "consolidation review payload must use consolidation source"
            raise ValueError(message)
        if self.retention_policy is not MemoryRetentionPolicy.REVIEW_REQUIRED:
            message = "consolidation review payload must require review"
            raise ValueError(message)
        if not self.review_required:
            message = "consolidation review payload must remain review_required"
            raise ValueError(message)
        if any(not candidate_id.strip() for candidate_id in self.source_candidate_ids):
            message = "source candidate ids must not be blank"
            raise ValueError(message)
        if any(not candidate_id.strip() for candidate_id in self.supersedes_candidate_ids):
            message = "superseded candidate ids must not be blank"
            raise ValueError(message)
        if set(self.supersedes_candidate_ids) - set(self.source_candidate_ids):
            message = "superseded candidate ids must reference source candidate ids"
            raise ValueError(message)
        return self


class ReviewSharedEpisodicMemoryCandidatePayload(BaseModel):
    """Shared episodic memory candidate review detail の typed payload。"""

    model_config = ConfigDict(frozen=True)

    summary: str = Field(min_length=1)
    kind: SharedEpisodicMemoryKind
    actor_id: ActorId
    account_id: AccountId
    space_id: SpaceId
    source_events: tuple[SharedEpisodicSourceEventRef, ...] = Field(min_length=1)
    occurred_at: datetime
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)
    review_required: bool
    admission_policy: SharedEpisodicAdmissionPolicy
    admission_risk: SharedEpisodicAdmissionRisk
    retrieval: SharedEpisodicRetrievalMetadata
    metadata: ImmutableMetadata = Field(default_factory=dict)

    @field_validator("summary", "reason")
    @classmethod
    def _text_fields_must_not_be_blank(cls, value: str) -> str:
        """空白だけの説明文を拒否する。

        Returns:
            検証済み文字列。

        Raises:
            ValueError: 空白だけの文字列の場合。
        """
        if not value.strip():
            message = "shared episodic memory review payload text fields must not be blank"
            raise ValueError(message)
        return value

    @model_validator(mode="after")
    def _validate_admission_policy(
        self,
    ) -> ReviewSharedEpisodicMemoryCandidatePayload:
        """Review payload でも shared episodic admission policy を強制する。

        Returns:
            検証済み payload。

        Raises:
            ValueError: admission policy が安全でない場合。
        """
        if (
            self.admission_risk is SharedEpisodicAdmissionRisk.SECRET_LIKE
            and self.admission_policy is not SharedEpisodicAdmissionPolicy.REJECT
        ):
            message = "secret-like shared episodic memories must be rejected"
            raise ValueError(message)
        if self.admission_policy is SharedEpisodicAdmissionPolicy.REVIEW_REQUIRED:
            if not self.review_required:
                message = "review_required must be true when admission policy is review_required"
                raise ValueError(message)
            return self
        if self.review_required:
            message = "review_required must be false when admission policy is reject"
            raise ValueError(message)
        return self


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
    shared_episodic_memory_candidate: ReviewSharedEpisodicMemoryCandidatePayload | None = None
    interaction_policy_candidate: ReviewInteractionPolicyCandidatePayload | None = None
    consolidation_candidate: ReviewConsolidationCandidatePayload | None = None
    created_at: datetime
    updated_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    review_reason: str | None = None
    promoted_memory_id: str | None = None
    metadata: ImmutableMetadata = Field(default_factory=dict)
    candidate_metadata: ImmutableMetadata = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_payload_matches_type(self) -> ReviewCandidateDetail:
        """candidate_type と typed payload の混在を拒否する。

        Returns:
            検証済み detail DTO。
        """
        if self.candidate_type is ReviewCandidateType.MEMORY:
            _validate_memory_detail_payloads(
                memory_candidate=self.memory_candidate,
                shared_episodic_memory_candidate=self.shared_episodic_memory_candidate,
                interaction_policy_candidate=self.interaction_policy_candidate,
                consolidation_candidate=self.consolidation_candidate,
            )
        elif self.candidate_type is ReviewCandidateType.SHARED_EPISODIC_MEMORY:
            shared_payload = _require_shared_episodic_detail_payload(
                memory_candidate=self.memory_candidate,
                shared_episodic_memory_candidate=self.shared_episodic_memory_candidate,
                interaction_policy_candidate=self.interaction_policy_candidate,
                consolidation_candidate=self.consolidation_candidate,
            )
            _validate_shared_episodic_scope(scope=self.scope, payload=shared_payload)
            _validate_shared_episodic_source_observation(
                source_observation_id=self.source_observation_id,
                payload=shared_payload,
            )
        elif self.candidate_type is ReviewCandidateType.INTERACTION_POLICY:
            _validate_interaction_policy_detail_payload(
                scope=self.scope,
                interaction_policy_candidate=self.interaction_policy_candidate,
                memory_candidate=self.memory_candidate,
                shared_episodic_memory_candidate=self.shared_episodic_memory_candidate,
                consolidation_candidate=self.consolidation_candidate,
            )
        elif self.candidate_type is ReviewCandidateType.CONSOLIDATION:
            _validate_consolidation_detail_payload(
                scope=self.scope,
                consolidation_candidate=self.consolidation_candidate,
                memory_candidate=self.memory_candidate,
                shared_episodic_memory_candidate=self.shared_episodic_memory_candidate,
                interaction_policy_candidate=self.interaction_policy_candidate,
            )
        else:
            _validate_future_detail_has_no_known_payloads(
                candidate_type=self.candidate_type,
                memory_candidate=self.memory_candidate,
                shared_episodic_memory_candidate=self.shared_episodic_memory_candidate,
                interaction_policy_candidate=self.interaction_policy_candidate,
                consolidation_candidate=self.consolidation_candidate,
            )
        return self


def _validate_memory_detail_payloads(
    *,
    memory_candidate: ReviewMemoryCandidatePayload | None,
    shared_episodic_memory_candidate: ReviewSharedEpisodicMemoryCandidatePayload | None,
    interaction_policy_candidate: ReviewInteractionPolicyCandidatePayload | None,
    consolidation_candidate: ReviewConsolidationCandidatePayload | None,
) -> None:
    """Memory detail に memory payload だけが載ることを検証する。

    Raises:
        ValueError: payload が不足または混在している場合。
    """
    if memory_candidate is None:
        message = "memory candidate detail requires memory payload"
        raise ValueError(message)
    if shared_episodic_memory_candidate is not None:
        message = "memory candidate detail must not include shared episodic payload"
        raise ValueError(message)
    if interaction_policy_candidate is not None:
        message = "memory candidate detail must not include interaction policy payload"
        raise ValueError(message)
    if consolidation_candidate is not None:
        message = "memory candidate detail must not include consolidation payload"
        raise ValueError(message)


def _require_shared_episodic_detail_payload(
    *,
    memory_candidate: ReviewMemoryCandidatePayload | None,
    shared_episodic_memory_candidate: ReviewSharedEpisodicMemoryCandidatePayload | None,
    interaction_policy_candidate: ReviewInteractionPolicyCandidatePayload | None,
    consolidation_candidate: ReviewConsolidationCandidatePayload | None,
) -> ReviewSharedEpisodicMemoryCandidatePayload:
    """Shared episodic detail の typed payload を返す。

    Returns:
        検証済み shared episodic payload。

    Raises:
        ValueError: payload が不足または混在している場合。
    """
    if shared_episodic_memory_candidate is None:
        message = "shared episodic memory detail requires shared episodic payload"
        raise ValueError(message)
    if (
        memory_candidate is not None
        or interaction_policy_candidate is not None
        or consolidation_candidate is not None
    ):
        message = "shared episodic memory detail must not include memory payload"
        raise ValueError(message)
    return shared_episodic_memory_candidate


def _validate_future_detail_has_no_known_payloads(
    *,
    candidate_type: ReviewCandidateType,
    memory_candidate: ReviewMemoryCandidatePayload | None,
    shared_episodic_memory_candidate: ReviewSharedEpisodicMemoryCandidatePayload | None,
    interaction_policy_candidate: ReviewInteractionPolicyCandidatePayload | None,
    consolidation_candidate: ReviewConsolidationCandidatePayload | None,
) -> None:
    """未実装 candidate type に既知 payload が混ざらないことを検証する。

    Raises:
        ValueError: candidate_type と payload が一致しない場合。
    """
    if memory_candidate is not None:
        message = f"{candidate_type.value} detail must not include memory payload"
        raise ValueError(message)
    if shared_episodic_memory_candidate is not None:
        message = f"{candidate_type.value} detail must not include shared episodic payload"
        raise ValueError(message)
    if interaction_policy_candidate is not None:
        message = f"{candidate_type.value} detail must not include interaction policy payload"
        raise ValueError(message)
    if consolidation_candidate is not None:
        message = f"{candidate_type.value} detail must not include consolidation payload"
        raise ValueError(message)


def _validate_interaction_policy_detail_payload(
    *,
    scope: ReviewCandidateScope,
    interaction_policy_candidate: ReviewInteractionPolicyCandidatePayload | None,
    memory_candidate: ReviewMemoryCandidatePayload | None,
    shared_episodic_memory_candidate: ReviewSharedEpisodicMemoryCandidatePayload | None,
    consolidation_candidate: ReviewConsolidationCandidatePayload | None,
) -> None:
    """Interaction policy detail の typed payload と scope を検証する。

    Raises:
        ValueError: payload が不足または scope が一致しない場合。
    """
    if interaction_policy_candidate is None:
        message = "interaction policy detail requires interaction policy payload"
        raise ValueError(message)
    if (
        memory_candidate is not None
        or shared_episodic_memory_candidate is not None
        or consolidation_candidate is not None
    ):
        message = "interaction policy detail must not include another candidate payload"
        raise ValueError(message)
    if scope.account_id != interaction_policy_candidate.account_id:
        message = "interaction policy scope account_id must match payload account_id"
        raise ValueError(message)
    if scope.space_id != interaction_policy_candidate.space_id:
        message = "interaction policy scope space_id must match payload space_id"
        raise ValueError(message)
    if scope.actor_id != interaction_policy_candidate.actor_id:
        message = "interaction policy scope actor_id must match payload actor_id"
        raise ValueError(message)


def _validate_consolidation_detail_payload(
    *,
    scope: ReviewCandidateScope,
    consolidation_candidate: ReviewConsolidationCandidatePayload | None,
    memory_candidate: ReviewMemoryCandidatePayload | None,
    shared_episodic_memory_candidate: ReviewSharedEpisodicMemoryCandidatePayload | None,
    interaction_policy_candidate: ReviewInteractionPolicyCandidatePayload | None,
) -> None:
    """Consolidation detail の typed payload と scope を検証する。

    Raises:
        ValueError: payload が不足、混在、または scope と不一致の場合。
    """
    if consolidation_candidate is None:
        message = "consolidation detail requires consolidation payload"
        raise ValueError(message)
    if (
        memory_candidate is not None
        or shared_episodic_memory_candidate is not None
        or interaction_policy_candidate is not None
    ):
        message = "consolidation detail must not include another candidate payload"
        raise ValueError(message)
    if scope.actor_id != consolidation_candidate.actor_id:
        message = "consolidation scope actor_id must match payload actor_id"
        raise ValueError(message)
    if scope.account_id != consolidation_candidate.account_id:
        message = "consolidation scope account_id must match payload account_id"
        raise ValueError(message)
    if scope.space_id != consolidation_candidate.space_id:
        message = "consolidation scope space_id must match payload space_id"
        raise ValueError(message)


def _validate_shared_episodic_scope(
    *,
    scope: ReviewCandidateScope,
    payload: ReviewSharedEpisodicMemoryCandidatePayload,
) -> None:
    """Shared episodic payload と review scope の境界不一致を拒否する。

    Raises:
        ValueError: scope と payload の actor/account/space が一致しない場合。
    """
    if scope.actor_id != payload.actor_id:
        message = "shared episodic scope actor_id must match payload actor_id"
        raise ValueError(message)
    if scope.account_id != payload.account_id:
        message = "shared episodic scope account_id must match payload account_id"
        raise ValueError(message)
    if scope.space_id != payload.space_id:
        message = "shared episodic scope space_id must match payload space_id"
        raise ValueError(message)


def _validate_shared_episodic_source_observation(
    *,
    source_observation_id: ObservationId | None,
    payload: ReviewSharedEpisodicMemoryCandidatePayload,
) -> None:
    """Detail の source observation が source event provenance と矛盾しないことを検証する。

    Raises:
        ValueError: detail の source observation が source event に含まれない場合。
    """
    if source_observation_id is None:
        return
    source_observation_ids = {event.observation_id for event in payload.source_events}
    if source_observation_id not in source_observation_ids:
        message = "shared episodic source_observation_id must reference a source event"
        raise ValueError(message)


class ReviewDecisionResult(BaseModel):
    """Review decision 適用結果。"""

    model_config = ConfigDict(frozen=True)

    candidate: ReviewCandidateDetail
    decision: ReviewDecisionKind
    changed: bool
