"""Account / space scoped interaction-policy candidate contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import NewType

from pydantic import BaseModel, ConfigDict, Field, model_validator

from iris.contracts.metadata import ImmutableMetadata
from iris.core.ids import AccountId, ActorId, SpaceId
from iris.core.metadata import immutable_metadata

InteractionPolicyCandidateId = NewType("InteractionPolicyCandidateId", str)


class InteractionPolicyKind(StrEnum):
    """Candidate が表す account / space 単位の応答方針。"""

    VERBOSITY = "verbosity"
    INITIATIVE = "initiative"
    TONE = "tone"


class InteractionPolicySourceKind(StrEnum):
    """候補の provenance。明示 feedback と反復 signal を分離する。"""

    EXPLICIT_FEEDBACK = "explicit_feedback"
    IMPLICIT_REPEATED_SIGNAL = "implicit_repeated_signal"
    MODEL_CLASSIFIER = "model_classifier"


class InteractionPolicyDecisionKind(StrEnum):
    """Deterministic baseline の candidate decision。"""

    REVIEW_REQUIRED = "review_required"
    SUPPRESSED = "suppressed"


class InteractionPolicySignal(BaseModel):
    """候補生成へ渡す一つの typed policy signal。"""

    model_config = ConfigDict(frozen=True)

    policy_kind: InteractionPolicyKind
    value: str = Field(min_length=1, max_length=160)
    source: InteractionPolicySourceKind
    source_event_id: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)
    occurred_at: datetime
    high_risk: bool = False
    model_metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)

    @model_validator(mode="after")
    def _validate_text(self) -> InteractionPolicySignal:
        """空白だけの policy value / provenance を拒否する。

        Returns:
            検証済み signal。

        Raises:
            ValueError: text field が空白だけの場合。
        """
        if not self.value.strip() or not self.source_event_id.strip() or not self.reason.strip():
            message = "interaction policy signal text fields must not be blank"
            raise ValueError(message)
        return self


class InteractionPolicyCandidate(BaseModel):
    """Review boundary に入る account / space scoped policy candidate。"""

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
    review_required: bool = True
    high_risk: bool = False
    model_metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)

    @model_validator(mode="after")
    def _validate_boundary(self) -> InteractionPolicyCandidate:
        """Review-only / scope / provenance の不変条件を検証する。

        Returns:
            検証済み candidate。

        Raises:
            ValueError: review-only boundary または provenance が不正な場合。
        """
        if not self.value.strip() or not self.reason.strip():
            message = "interaction policy candidate text fields must not be blank"
            raise ValueError(message)
        if any(not event_id.strip() for event_id in self.source_event_ids):
            message = "source_event_ids must not contain blank values"
            raise ValueError(message)
        if self.evidence_count != len(self.source_event_ids):
            message = "evidence_count must match source_event_ids"
            raise ValueError(message)
        if not self.review_required:
            message = "interaction policy candidates must remain review_required"
            raise ValueError(message)
        if self.decision_kind is InteractionPolicyDecisionKind.SUPPRESSED and not self.high_risk:
            message = "suppressed interaction policy candidates must be high_risk"
            raise ValueError(message)
        return self


class ApprovedInteractionPolicy(BaseModel):
    """明示承認後に prompt section へ渡せる scoped policy。"""

    model_config = ConfigDict(frozen=True)

    candidate_id: InteractionPolicyCandidateId
    policy_kind: InteractionPolicyKind
    value: str = Field(min_length=1, max_length=160)
    account_id: AccountId
    space_id: SpaceId | None = None
    approved_at: datetime
