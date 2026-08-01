"""配送前 final verifier の可用性を表す型付き契約。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class VerifierStatus(StrEnum):
    """Final verifier の外部観測可能な可用性状態。"""

    AVAILABLE = "available"
    WARMING = "warming"
    BUSY = "busy"
    UNAVAILABLE = "unavailable"


class VerifierAvailability(BaseModel):
    """Final verifier 可用性の決定論的 snapshot。"""

    model_config = ConfigDict(frozen=True)

    status: VerifierStatus
    reason: str
    observed_at: datetime


class DeliveryVerifierAvailabilityResolver(Protocol):
    """配送前に final verifier の可用性を解決する port。"""

    async def availability(self) -> VerifierAvailability:
        """現在の final verifier 可用性を返す。"""
        ...
