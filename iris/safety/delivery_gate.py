"""配送時刻・頻度・availability を検査する safety gate。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import TYPE_CHECKING, Protocol
from zoneinfo import ZoneInfo

from iris.contracts.availability import AvailabilityStatus

if TYPE_CHECKING:
    from iris.contracts.actions import PresentedOutput
    from iris.contracts.availability import AvailabilitySnapshot
    from iris.contracts.delivery import DeliveryTarget


@dataclass(frozen=True)
class QuietHoursPolicy:
    """配送 quiet hours 設定。"""

    enabled: bool = False
    start: time = time(hour=22)
    end: time = time(hour=8)
    timezone: str = "Asia/Tokyo"


@dataclass(frozen=True)
class DeliverySafetyDecision:
    """配送 safety gate の決定。"""

    allowed: bool
    reason: str
    not_before: datetime | None = None


class DeliverySafetyGate(Protocol):
    """PresentedOutput を配送 outbox へ入れてよいか判定する port。"""

    async def check(
        self,
        *,
        target: DeliveryTarget,
        output: PresentedOutput,
        availability: AvailabilitySnapshot | None,
        now: datetime,
    ) -> DeliverySafetyDecision:
        """配送可否を決定する。

        Returns:
            DeliverySafetyDecision: 配送可否と理由。
        """
        ...


@dataclass(frozen=True)
class BasicDeliverySafetyGate:
    """決定論的な最小配送 safety gate。"""

    quiet_hours: QuietHoursPolicy = QuietHoursPolicy()

    async def check(
        self,
        *,
        target: DeliveryTarget,
        output: PresentedOutput,
        availability: AvailabilitySnapshot | None,
        now: datetime,
    ) -> DeliverySafetyDecision:
        """配送 target、availability、時刻から配送可否を返す。

        Returns:
            DeliverySafetyDecision: 配送可否と理由。blocked の場合は not_before を含む。
        """
        reason = self._blocking_reason(target, output, availability, now)
        if reason is not None:
            return DeliverySafetyDecision(allowed=False, reason=reason)
        return DeliverySafetyDecision(allowed=True, reason="allowed")

    def _blocking_reason(
        self,
        target: DeliveryTarget,
        output: PresentedOutput,
        availability: AvailabilitySnapshot | None,
        now: datetime,
    ) -> str | None:
        """最初に hit した block 理由を返す。

        Returns:
            block 理由。全て通過する場合は None。
        """
        for reason in (
            self._output_reason(output),
            self._target_reason(target),
            self._availability_reason(availability),
            self._quiet_hours_reason(now),
        ):
            if reason is not None:
                return reason
        return None

    @staticmethod
    def _output_reason(output: PresentedOutput) -> str | None:
        """送信不可 output の理由を返す。

        Returns:
            block 理由または None。
        """
        if not output.is_sendable:
            return "output_not_sendable"
        return None

    @staticmethod
    def _target_reason(target: DeliveryTarget) -> str | None:
        """配送先 routing 不備の理由を返す。

        Returns:
            block 理由または None。
        """
        if not target.provider:
            return "missing_provider"
        if target.provider_subject is None and target.provider_space_ref is None:
            return "missing_route"
        return None

    @staticmethod
    def _availability_reason(availability: AvailabilitySnapshot | None) -> str | None:
        """可用性による block 理由を返す。

        Returns:
            block 理由または None。
        """
        if availability is None:
            return None
        return {
            AvailabilityStatus.BUSY: "availability_busy",
            AvailabilityStatus.UNAVAILABLE: "availability_unavailable",
        }.get(availability.status)

    def _quiet_hours_reason(self, now: datetime) -> str | None:
        """静寂時間帯内なら block 理由を返す。

        Returns:
            block 理由または None。
        """
        if not self.quiet_hours.enabled:
            return None
        local_now = now.astimezone(ZoneInfo(self.quiet_hours.timezone))
        current = local_now.time()
        start = self.quiet_hours.start
        end = self.quiet_hours.end
        in_window = start <= current < end if start < end else current >= start or current < end
        if in_window:
            return "quiet_hours"
        return None
