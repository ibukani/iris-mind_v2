"""決定論的メモリ統合の typed contract。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from iris.contracts.memory import MemoryKind
from iris.contracts.memory_candidates import (
    MemoryCandidateSensitivity,
    MemoryCandidateSource,
    MemoryRetentionPolicy,
)
from iris.contracts.metadata import ImmutableMetadata
from iris.core.ids import AccountId, ActorId, ObservationId, SpaceId
from iris.core.metadata import immutable_metadata


class MemoryConsolidationDecisionKind(StrEnum):
    """統合 worker が返す deterministic decision。"""

    RETAINED = "retained"
    DUPLICATE = "duplicate"
    STALE = "stale"
    CONFLICT = "conflict"
    SUPERSEDED = "superseded"


class MemoryConsolidationSourceCandidate(BaseModel):
    """統合対象となる review candidate の immutable snapshot。"""

    model_config = ConfigDict(frozen=True)

    source_candidate_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    kind: MemoryKind
    salience: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    source: MemoryCandidateSource
    reason: str | None = None
    retention_policy: MemoryRetentionPolicy
    sensitivity: MemoryCandidateSensitivity = MemoryCandidateSensitivity.NORMAL
    actor_id: ActorId | None = None
    account_id: AccountId | None = None
    space_id: SpaceId | None = None
    source_observation_id: ObservationId | None = None
    created_at: datetime
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


class MemoryConsolidationJobPayload(BaseModel):
    """決定論的統合 worker へ渡す候補 snapshot 群。"""

    model_config = ConfigDict(frozen=True)

    candidates: tuple[MemoryConsolidationSourceCandidate, ...] = Field(min_length=1)


class MemoryConsolidationCandidate(BaseModel):
    """統合結果として review boundary へ渡す候補。"""

    model_config = ConfigDict(frozen=True)

    candidate_id: str = Field(min_length=1)
    proposed: MemoryConsolidationSourceCandidate
    decision_kind: MemoryConsolidationDecisionKind
    source_candidate_ids: tuple[str, ...] = Field(min_length=1)
    supersedes_candidate_ids: tuple[str, ...] = ()
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)
    review_required: bool = True
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)

    @model_validator(mode="after")
    def _validate_review_boundary(self) -> MemoryConsolidationCandidate:
        """統合結果が暗黙昇格されないことを検証する。

        Returns:
            検証済みの統合候補。

        Raises:
            ValueError: review-only contract または source provenance が不正な場合。
        """
        if not self.review_required:
            message = "memory consolidation candidates must remain review_required"
            raise ValueError(message)
        if self.proposed.source_candidate_id not in self.source_candidate_ids:
            message = "proposed candidate must reference a source candidate"
            raise ValueError(message)
        if any(not candidate_id.strip() for candidate_id in self.source_candidate_ids):
            message = "source candidate ids must not be blank"
            raise ValueError(message)
        if any(not candidate_id.strip() for candidate_id in self.supersedes_candidate_ids):
            message = "superseded candidate ids must not be blank"
            raise ValueError(message)
        if set(self.supersedes_candidate_ids) - set(self.source_candidate_ids):
            message = "superseded candidates must be source candidates"
            raise ValueError(message)
        return self
