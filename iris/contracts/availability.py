"""ランタイムから導出される availability 契約。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator

from iris.core.ids import ActorId


class AvailabilityStatus(StrEnum):
    """アクターが相互作用可能かどうかの、ランタイムから導出された推定値。"""

    UNKNOWN = "unknown"
    AVAILABLE = "available"
    INTERRUPTIBLE = "interruptible"
    PASSIVE = "passive"
    BUSY = "busy"
    UNAVAILABLE = "unavailable"


class AvailabilitySnapshot(BaseModel):
    """アクターの availability を表す、ランタイムから導出されたスナップショット。"""

    model_config = ConfigDict(frozen=True)

    actor_id: ActorId | None
    status: AvailabilityStatus
    reason: str
    observed_at: datetime | None
    computed_at: datetime
    confidence: float = 1.0

    @model_validator(mode="after")
    def _validate_confidence(self) -> AvailabilitySnapshot:
        """Confidence が有効範囲内にあることを検証する。"""
        if not 0.0 <= self.confidence <= 1.0:
            message = "confidence must be between 0.0 and 1.0"
            raise ValueError(message)
        return self
