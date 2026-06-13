"""ランタイムから導出される availability 契約。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from iris.core.ids import ActorId


class AvailabilityStatus(StrEnum):
    """アクターが相互作用可能かどうかの、ランタイムから導出された推定値。"""

    UNKNOWN = "unknown"
    AVAILABLE = "available"
    INTERRUPTIBLE = "interruptible"
    PASSIVE = "passive"
    BUSY = "busy"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class AvailabilitySnapshot:
    """アクターの availability を表す、ランタイムから導出されたスナップショット。"""

    actor_id: ActorId | None
    status: AvailabilityStatus
    reason: str
    observed_at: datetime | None
    computed_at: datetime
    confidence: float = 1.0

    def __post_init__(self) -> None:
        """Confidence が有効範囲内にあることを検証する。

        Raises:
            ValueError: confidence が 0.0 未満または 1.0 を超える場合。
        """
        if not 0.0 <= self.confidence <= 1.0:
            message = "confidence must be between 0.0 and 1.0"
            raise ValueError(message)
