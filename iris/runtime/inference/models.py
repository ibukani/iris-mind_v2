"""ローカル推論資源 scheduler boundary の共有モデル。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from iris.contracts.metadata import ImmutableMetadata
from iris.contracts.model_policy import ModelCallSite
from iris.core.metadata import immutable_metadata


class InferenceResourceState(StrEnum):
    """ローカル推論資源の外部観測可能な状態。"""

    IDLE = "idle"
    BUSY = "busy"
    WARMING = "warming"
    UNAVAILABLE = "unavailable"


class InferenceSlotKind(StrEnum):
    """scheduler が管理する推論 slot 種別。"""

    LARGE_LLM = "large_llm"
    BACKGROUND_LLM = "background_llm"
    SMALL_CLASSIFIER = "small_classifier"
    EMBEDDING = "embedding"
    RERANKER = "reranker"


class InferenceWorkPriority(StrEnum):
    """推論資源 lease 要求の優先度。"""

    USER_FACING_RESPONSE = "user_facing_response"
    SAFETY_CRITICAL = "safety_critical"
    BACKGROUND = "background"
    PROACTIVE = "proactive"


class InferenceLeaseDecision(StrEnum):
    """非blocking lease 判定。"""

    ACQUIRED = "acquired"
    DEFER = "defer"
    CANCEL = "cancel"
    NO_SEND = "no_send"
    DENIED = "denied"


class InferenceLeaseRequest(BaseModel):
    """推論資源 lease の安全な要求メタデータ。"""

    model_config = ConfigDict(frozen=True)

    slot_kind: InferenceSlotKind
    priority: InferenceWorkPriority
    call_site: ModelCallSite
    model_slot: str | None = None
    model_name: str | None = None
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


class InferenceResourceSnapshot(BaseModel):
    """scheduler の観測可能な resource snapshot。"""

    model_config = ConfigDict(frozen=True)

    state: InferenceResourceState
    active_large_slots: int = 0
    active_small_classifier_slots: int = 0
    active_embedding_slots: int = 0
    active_reranker_slots: int = 0
    busy_since: datetime | None = None
    busy_duration_seconds: float | None = None


class InferenceLeaseResult(BaseModel):
    """lease acquisition の決定論的な結果。"""

    model_config = ConfigDict(frozen=True)

    decision: InferenceLeaseDecision
    reason: str
    request: InferenceLeaseRequest
    snapshot: InferenceResourceSnapshot
    lease_id: str | None = None
    cancelled_lease_ids: tuple[str, ...] = ()

    @property
    def acquired(self) -> bool:
        """推論資源を取得できた場合に True。"""
        return self.decision is InferenceLeaseDecision.ACQUIRED


def model_call_site_priority(site: ModelCallSite) -> InferenceWorkPriority:
    """ModelCallSite を #93 scheduler priority に写像する。

    Returns:
        InferenceWorkPriority: site に対応する推論資源優先度。
    """
    if site is ModelCallSite.USER_RESPONSE_HOT_PATH:
        return InferenceWorkPriority.USER_FACING_RESPONSE
    if site is ModelCallSite.PROACTIVE:
        return InferenceWorkPriority.PROACTIVE
    return InferenceWorkPriority.BACKGROUND
