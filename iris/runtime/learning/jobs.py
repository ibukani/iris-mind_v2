"""バックグラウンド学習ジョブの型付きモデル。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import NewType

from pydantic import BaseModel, ConfigDict, Field

from iris.contracts.appraisal import AppraisalSignal
from iris.contracts.companion_affect import CompanionInteractionScope
from iris.contracts.interaction_policy import InteractionPolicySignal
from iris.contracts.learning import RuntimeLearningEventKind
from iris.contracts.memory import MemoryKind
from iris.contracts.memory_candidates import (
    MemoryCandidateSensitivity,
    MemoryCandidateSource,
    MemoryRetentionPolicy,
)
from iris.contracts.memory_consolidation import MemoryConsolidationJobPayload
from iris.contracts.model_policy import ModelCallDescriptor
from iris.contracts.observations import ObservationKind, UserFeedbackKind
from iris.core.ids import AccountId, ActorId, ObservationId, SessionId, SpaceId

BackgroundJobId = NewType("BackgroundJobId", str)


class BackgroundJobStatus(StrEnum):
    """バックグラウンドジョブのライフサイクル状態。"""

    PENDING = "pending"
    LEASED = "leased"
    SUCCEEDED = "succeeded"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_PERMANENT = "failed_permanent"
    CANCELLED = "cancelled"


class BackgroundJobKind(StrEnum):
    """現在および将来の学習ジョブ種別。"""

    MEMORY_EXTRACTION = "memory_extraction"
    MEMORY_CONSOLIDATION = "memory_consolidation"
    RELATIONSHIP_UPDATE = "relationship_update"
    INTERACTION_POLICY_CANDIDATE = "interaction_policy_candidate"
    PERSONA_PATCH_PROPOSAL = "persona_patch_proposal"
    EPISODIC_TO_SEMANTIC_PROMOTION = "episodic_to_semantic_promotion"
    REFLECTION = "reflection"
    LANGMEM_EXTRACTION = "langmem_extraction"


class BackgroundJobResourceProfile(BaseModel):
    """ジョブが推論資源を使うかを表す lightweight metadata。"""

    model_config = ConfigDict(frozen=True)

    uses_llm: bool = False
    idle_only: bool = False
    model_call_descriptor: ModelCallDescriptor | None = None


class MemoryBackgroundJobPayload(BaseModel):
    """決定論的メモリ処理に渡す明示的な入力。"""

    model_config = ConfigDict(frozen=True)

    text: str
    memory_kind: MemoryKind
    source: MemoryCandidateSource
    reason: str | None
    retention_policy: MemoryRetentionPolicy
    sensitivity: MemoryCandidateSensitivity = MemoryCandidateSensitivity.NORMAL
    review_required: bool
    salience: float
    confidence: float
    actor_id: ActorId | None = None
    account_id: AccountId | None = None
    space_id: SpaceId | None = None
    source_observation_id: ObservationId | None = None


class RuntimeLearningCandidateJobPayload(BaseModel):
    """RuntimeLearningEventから候補抽出へ渡すtyped payload。"""

    model_config = ConfigDict(frozen=True)

    event_kind: RuntimeLearningEventKind
    route: str
    observation_kind: ObservationKind
    input_text: str | None = None
    output_text: str | None = None
    feedback_kind: UserFeedbackKind | None = None
    actor_id: ActorId | None = None
    account_id: AccountId | None = None
    space_id: SpaceId | None = None
    session_id: SessionId
    source_observation_id: ObservationId
    occurred_at: datetime


class DeferredLearningJobPayload(BaseModel):
    """高度な将来処理向けの、不透明値を持たない最小入力。"""

    model_config = ConfigDict(frozen=True)

    source_observation_id: ObservationId | None = None
    reason: str | None = None


class RelationshipUpdateJobPayload(BaseModel):
    """Typed appraisal signal を relationship candidate worker に渡す入力。"""

    model_config = ConfigDict(frozen=True)

    signals: tuple[AppraisalSignal, ...] = Field(min_length=1)
    interaction_scope: CompanionInteractionScope
    actor_id: ActorId
    account_id: AccountId | None = None
    space_id: SpaceId | None = None
    source_observation_id: ObservationId | None = None
    source_event_ids: tuple[str, ...] = ()


class InteractionPolicyJobPayload(BaseModel):
    """Interaction policy candidate worker へ渡す scoped signal。"""

    model_config = ConfigDict(frozen=True)

    signals: tuple[InteractionPolicySignal, ...] = Field(min_length=1)
    account_id: AccountId
    space_id: SpaceId | None = None
    actor_id: ActorId | None = None


BackgroundJobPayload = (
    MemoryBackgroundJobPayload
    | RuntimeLearningCandidateJobPayload
    | DeferredLearningJobPayload
    | RelationshipUpdateJobPayload
    | InteractionPolicyJobPayload
    | MemoryConsolidationJobPayload
)


class BackgroundJobRecord(BaseModel):
    """キューが管理するバックグラウンドジョブ。"""

    model_config = ConfigDict(frozen=True)

    job_id: BackgroundJobId
    kind: BackgroundJobKind
    payload: BackgroundJobPayload
    status: BackgroundJobStatus = BackgroundJobStatus.PENDING
    attempts: int = 0
    max_attempts: int = 3
    not_before: datetime
    resource_profile: BackgroundJobResourceProfile = Field(
        default_factory=BackgroundJobResourceProfile
    )
    leased_until: datetime | None = None
    idempotency_key: str
    created_at: datetime
    updated_at: datetime
    last_error: str | None = None
    defer_reason: str | None = None
