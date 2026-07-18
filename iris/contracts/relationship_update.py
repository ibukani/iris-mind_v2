"""Relationship update policy v2 の型付き契約。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, NewType, Protocol

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from iris.contracts.appraisal import AppraisalSignalKind
from iris.contracts.companion_affect import CompanionAffectStateKind, CompanionInteractionScope
from iris.contracts.metadata import ImmutableMetadata
from iris.core.ids import AccountId, ActorId, ObservationId, SpaceId
from iris.core.metadata import immutable_metadata

_ZERO_DELTA_EPSILON = 1e-12

RelationshipUpdateCandidateId = NewType("RelationshipUpdateCandidateId", str)


def _validate_source_event_ids(value: tuple[str, ...]) -> tuple[str, ...]:
    """空白だけの source event id を拒否する。

    Returns:
        検証済み source event IDs。

    Raises:
        ValueError: source event id が空白だけの場合。
    """
    if any(not source_event_id.strip() for source_event_id in value):
        message = "source_event_ids must not contain blank values"
        raise ValueError(message)
    return value


type _SourceEventIds = Annotated[tuple[str, ...], AfterValidator(_validate_source_event_ids)]


class RelationshipUpdateDecisionKind(StrEnum):
    """Relationship update policy が返す decision 種別。"""

    AUTOMATIC_BOUNDED = "automatic_bounded"
    REVIEW_REQUIRED = "review_required"
    SUPPRESSED = "suppressed"


class RelationshipUpdateReasonKind(StrEnum):
    """Relationship update candidate の typed reason 種別。"""

    POSITIVE_ATTITUDE_TOWARD_IRIS = "positive_attitude_toward_iris"
    NEGATIVE_ATTITUDE_TOWARD_IRIS = "negative_attitude_toward_iris"
    LOW_CONFIDENCE_ATTITUDE = "low_confidence_attitude"
    HIGH_MAGNITUDE_ATTITUDE = "high_magnitude_attitude"
    ZERO_DELTA_ATTITUDE = "zero_delta_attitude"
    NON_RELATIONSHIP_SIGNAL = "non_relationship_signal"
    DEPENDENCY_RISK_BOUNDARY = "dependency_risk_boundary"


class RelationshipUpdateSourceKind(StrEnum):
    """Relationship update candidate の source 種別。"""

    APPRAISAL_SIGNAL = "appraisal_signal"


class RelationshipStateDelta(BaseModel):
    """ActorRelationshipState に適用し得る bounded delta。"""

    model_config = ConfigDict(frozen=True)

    affinity: float = Field(default=0.0, ge=-1.0, le=1.0)
    trust: float = Field(default=0.0, ge=-1.0, le=1.0)
    familiarity: float = Field(default=0.0, ge=-1.0, le=1.0)

    @property
    def max_abs_component(self) -> float:
        """Delta の最大絶対成分を返す。"""
        return max(abs(self.affinity), abs(self.trust), abs(self.familiarity))

    @property
    def is_zero(self) -> bool:
        """Delta が実質的にゼロかを返す。"""
        return self.max_abs_component <= _ZERO_DELTA_EPSILON


class RelationshipDeltaBounds(BaseModel):
    """Relationship delta に適用する cap。"""

    model_config = ConfigDict(frozen=True)

    max_abs_affinity_delta: float = Field(ge=0.0, le=1.0)
    max_abs_trust_delta: float = Field(ge=0.0, le=1.0)
    max_abs_familiarity_delta: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_non_empty_bounds(self) -> RelationshipDeltaBounds:
        """少なくとも1つの relationship 成分に cap があることを検証する。

        Returns:
            検証済み bounds。

        Raises:
            ValueError: 全 delta cap が 0 の場合。
        """
        if (
            self.max_abs_affinity_delta <= 0.0
            and self.max_abs_trust_delta <= 0.0
            and self.max_abs_familiarity_delta <= 0.0
        ):
            message = "at least one relationship delta bound must be positive"
            raise ValueError(message)
        return self


def _bounds_exceed(
    candidate_bounds: RelationshipDeltaBounds,
    reference_bounds: RelationshipDeltaBounds,
) -> bool:
    return (
        candidate_bounds.max_abs_affinity_delta > reference_bounds.max_abs_affinity_delta
        or candidate_bounds.max_abs_trust_delta > reference_bounds.max_abs_trust_delta
        or candidate_bounds.max_abs_familiarity_delta > reference_bounds.max_abs_familiarity_delta
    )


class RelationshipUpdatePolicyConfig(BaseModel):
    """Config v2 以前に docs / tests で固定する policy constants。"""

    model_config = ConfigDict(frozen=True)

    min_automatic_confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    high_magnitude_review_threshold: float = Field(default=0.025, ge=0.0, le=1.0)
    direct_message_bounds: RelationshipDeltaBounds = Field(
        default_factory=lambda: RelationshipDeltaBounds(
            max_abs_affinity_delta=0.03,
            max_abs_trust_delta=0.01,
        )
    )
    group_space_bounds: RelationshipDeltaBounds = Field(
        default_factory=lambda: RelationshipDeltaBounds(
            max_abs_affinity_delta=0.015,
            max_abs_trust_delta=0.005,
        )
    )

    @model_validator(mode="after")
    def _validate_policy_bounds(self) -> RelationshipUpdatePolicyConfig:
        """Policy bounds の不変条件を検証する。

        Returns:
            検証済み policy config。

        Raises:
            ValueError: threshold が全 relationship delta cap を超える場合、
                または group-space cap が DM cap を超える場合。
        """
        if _bounds_exceed(self.group_space_bounds, self.direct_message_bounds):
            message = "group_space_bounds must not exceed direct_message_bounds"
            raise ValueError(message)
        max_configured_bound = max(
            self.direct_message_bounds.max_abs_affinity_delta,
            self.direct_message_bounds.max_abs_trust_delta,
            self.direct_message_bounds.max_abs_familiarity_delta,
            self.group_space_bounds.max_abs_affinity_delta,
            self.group_space_bounds.max_abs_trust_delta,
            self.group_space_bounds.max_abs_familiarity_delta,
        )
        if self.high_magnitude_review_threshold > max_configured_bound:
            message = "high_magnitude_review_threshold must not exceed configured bounds"
            raise ValueError(message)
        return self

    def bounds_for_scope(self, scope: CompanionInteractionScope) -> RelationshipDeltaBounds:
        """Interaction scope に対応する cap を返す。

        Returns:
            DM / group-space 用の relationship delta bounds。
        """
        if scope is CompanionInteractionScope.DIRECT_MESSAGE:
            return self.direct_message_bounds
        return self.group_space_bounds


RELATIONSHIP_UPDATE_POLICY_DEFAULTS = RelationshipUpdatePolicyConfig()
"""Relationship update policy v2 の初期固定値。Runtime Config v2 までは編集可能にしない。"""


class RelationshipUpdateSourceRef(BaseModel):
    """Candidate の根拠となった typed appraisal signal 参照。"""

    model_config = ConfigDict(frozen=True)

    source_kind: Literal[RelationshipUpdateSourceKind.APPRAISAL_SIGNAL] = (
        RelationshipUpdateSourceKind.APPRAISAL_SIGNAL
    )
    signal_kind: AppraisalSignalKind
    source_observation_id: ObservationId | None = None
    source_event_ids: _SourceEventIds = ()
    source_reason: str = Field(min_length=1)
    source_confidence: float = Field(ge=0.0, le=1.0)


class RelationshipUpdateCandidate(BaseModel):
    """#72 worker が参照できる relationship update candidate。"""

    model_config = ConfigDict(frozen=True)

    target_state_kind: Literal[CompanionAffectStateKind.ACTOR_RELATIONSHIP] = (
        CompanionAffectStateKind.ACTOR_RELATIONSHIP
    )
    decision_kind: RelationshipUpdateDecisionKind
    delta: RelationshipStateDelta
    bounds: RelationshipDeltaBounds
    reason_kind: RelationshipUpdateReasonKind
    reason: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    source_refs: tuple[RelationshipUpdateSourceRef, ...] = Field(min_length=1)
    source_observation_ids: tuple[ObservationId, ...] = ()
    source_event_ids: _SourceEventIds = ()
    review_required: bool = False
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)

    @model_validator(mode="after")
    def _validate_decision(self) -> RelationshipUpdateCandidate:
        """Decision / bounds / provenance の不変条件を検証する。

        Returns:
            検証済み candidate。

        Raises:
            ValueError: decision / bounds / provenance が矛盾する場合。
        """
        _validate_delta_within_bounds(self.delta, self.bounds)
        if self.source_observation_ids != _source_observation_ids(self.source_refs):
            message = "source_observation_ids must match source_refs"
            raise ValueError(message)
        if self.source_event_ids != _source_event_ids(self.source_refs):
            message = "source_event_ids must match source_refs"
            raise ValueError(message)
        if self.decision_kind is RelationshipUpdateDecisionKind.AUTOMATIC_BOUNDED:
            self._validate_automatic_bounded()
        elif self.decision_kind is RelationshipUpdateDecisionKind.REVIEW_REQUIRED:
            self._validate_review_required()
        else:
            self._validate_suppressed()
        return self

    def _validate_automatic_bounded(self) -> None:
        """Automatic bounded candidate の不変条件を検証する。

        Raises:
            ValueError: automatic bounded candidate として不正な場合。
        """
        if self.review_required:
            message = "automatic bounded updates must not be review_required"
            raise ValueError(message)
        if self.delta.is_zero:
            message = "automatic bounded updates require a non-zero delta"
            raise ValueError(message)

    def _validate_review_required(self) -> None:
        """Review-required candidate の不変条件を検証する。

        Raises:
            ValueError: review-required decision と flag が一致しない場合。
        """
        if not self.review_required:
            message = "review_required decision must set review_required=True"
            raise ValueError(message)
        if self.delta.is_zero:
            message = "review_required updates require a non-zero delta"
            raise ValueError(message)

    def _validate_suppressed(self) -> None:
        """Suppressed candidate の不変条件を検証する。

        Raises:
            ValueError: suppressed candidate が non-zero delta などを持つ場合。
        """
        if self.review_required:
            message = "suppressed updates must not be review_required"
            raise ValueError(message)
        if not self.delta.is_zero:
            message = "suppressed updates must use a zero delta"
            raise ValueError(message)


class RelationshipUpdatePolicyResult(BaseModel):
    """Relationship update policy v2 の pure decision result。"""

    model_config = ConfigDict(frozen=True)

    interaction_scope: CompanionInteractionScope
    candidates: tuple[RelationshipUpdateCandidate, ...] = ()

    @property
    def automatic_candidates(self) -> tuple[RelationshipUpdateCandidate, ...]:
        """Automatic bounded candidate だけを返す。"""
        return self.candidates_by_decision(RelationshipUpdateDecisionKind.AUTOMATIC_BOUNDED)

    @property
    def review_required_candidates(self) -> tuple[RelationshipUpdateCandidate, ...]:
        """Review-required candidate だけを返す。"""
        return self.candidates_by_decision(RelationshipUpdateDecisionKind.REVIEW_REQUIRED)

    @property
    def suppressed_candidates(self) -> tuple[RelationshipUpdateCandidate, ...]:
        """Suppressed candidate だけを返す。"""
        return self.candidates_by_decision(RelationshipUpdateDecisionKind.SUPPRESSED)

    def candidates_by_decision(
        self,
        decision_kind: RelationshipUpdateDecisionKind,
    ) -> tuple[RelationshipUpdateCandidate, ...]:
        """Decision kind で candidate を絞り込む。

        Returns:
            指定 decision kind に一致する candidate 群。
        """
        return tuple(
            candidate for candidate in self.candidates if candidate.decision_kind is decision_kind
        )


class RelationshipUpdateCandidateRecord(BaseModel):
    """Worker が durable state の手前で保持する candidate record。"""

    model_config = ConfigDict(frozen=True)

    candidate_id: RelationshipUpdateCandidateId
    candidate: RelationshipUpdateCandidate
    interaction_scope: CompanionInteractionScope
    actor_id: ActorId
    account_id: AccountId | None = None
    space_id: SpaceId | None = None
    created_at: datetime
    updated_at: datetime
    idempotency_key: str = Field(min_length=1)


class RelationshipUpdateCandidateStore(Protocol):
    """Relationship candidate を durable state へ昇格する前の store。"""

    def add_nowait(
        self,
        record: RelationshipUpdateCandidateRecord,
    ) -> RelationshipUpdateCandidateRecord:
        """Candidate を idempotent に追加する。"""
        ...


def _validate_delta_within_bounds(
    delta: RelationshipStateDelta,
    bounds: RelationshipDeltaBounds,
) -> None:
    if abs(delta.affinity) > bounds.max_abs_affinity_delta:
        message = "affinity delta exceeds bounds"
        raise ValueError(message)
    if abs(delta.trust) > bounds.max_abs_trust_delta:
        message = "trust delta exceeds bounds"
        raise ValueError(message)
    if abs(delta.familiarity) > bounds.max_abs_familiarity_delta:
        message = "familiarity delta exceeds bounds"
        raise ValueError(message)


def _source_observation_ids(
    source_refs: tuple[RelationshipUpdateSourceRef, ...],
) -> tuple[ObservationId, ...]:
    return tuple(
        source_ref.source_observation_id
        for source_ref in source_refs
        if source_ref.source_observation_id is not None
    )


def _source_event_ids(source_refs: tuple[RelationshipUpdateSourceRef, ...]) -> tuple[str, ...]:
    return tuple(
        source_event_id
        for source_ref in source_refs
        for source_event_id in source_ref.source_event_ids
    )
