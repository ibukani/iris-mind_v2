"""Raw content を保持しない runtime safety audit journal。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, override

if TYPE_CHECKING:
    from datetime import datetime

    from iris.core.ids import ObservationId
    from iris.safety.policy_engine import DeliverySource, SafetyRiskLevel


class SafetyAuditStage(StrEnum):
    """Safety decision が発生した境界。"""

    OUTPUT = "output"
    DELIVERY = "delivery"


@dataclass(frozen=True)
class SafetyAuditRecord:
    """User text や生成 text を含まない safety decision 記録。"""

    observation_id: ObservationId
    occurred_at: datetime
    stage: SafetyAuditStage
    allowed: bool
    reason: str
    risk_level: SafetyRiskLevel
    source: DeliverySource
    target_key: str
    policy: str
    policy_version: str


class SafetyAuditJournal(Protocol):
    """Safety decision の append/query port。"""

    async def append(self, record: SafetyAuditRecord) -> None:
        """Safety decision を追加する。"""
        ...

    async def recent_block_count(self, target_key: str, *, since: datetime) -> int:
        """同じ target の期間内 block 数を返す。"""
        ...


class InMemorySafetyAuditJournal(SafetyAuditJournal):
    """Process-local bounded safety audit journal。"""

    def __init__(self, max_records: int = 1024) -> None:
        """最大保持件数を指定して初期化する。

        Raises:
            ValueError: max_records が1未満の場合。
        """
        if max_records < 1:
            message = "max_records must be at least 1"
            raise ValueError(message)
        self._records: deque[SafetyAuditRecord] = deque(maxlen=max_records)

    @override
    async def append(self, record: SafetyAuditRecord) -> None:
        """Record を journal に追加する。"""
        self._records.append(record)

    @override
    async def recent_block_count(self, target_key: str, *, since: datetime) -> int:
        """同じ target の delivery block 数を数える。

        Returns:
            期間内の block 件数。
        """
        return sum(
            1
            for record in self._records
            if record.target_key == target_key
            and record.stage is SafetyAuditStage.DELIVERY
            and not record.allowed
            and record.occurred_at >= since
        )

    def records(self) -> tuple[SafetyAuditRecord, ...]:
        """テスト・診断用 immutable snapshot を返す。

        Returns:
            現在保持する record の immutable snapshot。
        """
        return tuple(self._records)
