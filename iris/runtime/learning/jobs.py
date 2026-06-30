"""バックグラウンド学習ジョブの型付きモデル。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import NewType

from pydantic import BaseModel, ConfigDict

from iris.cognitive.memory.candidates import (
    MemoryCandidateSource,
    MemoryRetentionPolicy,
)
from iris.contracts.memory import MemoryKind
from iris.core.ids import ActorId, ObservationId, SpaceId

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
    PERSONA_PATCH_PROPOSAL = "persona_patch_proposal"
    EPISODIC_TO_SEMANTIC_PROMOTION = "episodic_to_semantic_promotion"
    REFLECTION = "reflection"
    LANGMEM_EXTRACTION = "langmem_extraction"


class MemoryBackgroundJobPayload(BaseModel):
    """決定論的メモリ処理に渡す明示的な入力。"""

    model_config = ConfigDict(frozen=True)

    text: str
    memory_kind: MemoryKind
    source: MemoryCandidateSource
    reason: str | None
    retention_policy: MemoryRetentionPolicy
    review_required: bool
    salience: float
    confidence: float
    actor_id: ActorId | None = None
    space_id: SpaceId | None = None
    source_observation_id: ObservationId | None = None


class DeferredLearningJobPayload(BaseModel):
    """高度な将来処理向けの、不透明値を持たない最小入力。"""

    model_config = ConfigDict(frozen=True)

    source_observation_id: ObservationId | None = None
    reason: str | None = None


BackgroundJobPayload = MemoryBackgroundJobPayload | DeferredLearningJobPayload


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
    leased_until: datetime | None = None
    idempotency_key: str
    created_at: datetime
    updated_at: datetime
    last_error: str | None = None
