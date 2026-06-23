"""Runtime scheduler port."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import datetime

    from iris.contracts.availability import AvailabilitySnapshot
    from iris.contracts.delivery import DeliveryTarget
    from iris.core.ids import ObservationId
    from iris.runtime.scheduler.models import ScheduledObservation


class RuntimeScheduler(Protocol):
    """Due observations を提供する scheduler port。"""

    async def due_observations(
        self,
        now: datetime,
    ) -> tuple[ScheduledObservation, ...]:
        """現在 due の typed observations を返す。"""
        ...

    async def mark_dispatched(
        self,
        observation_id: ObservationId,
        *,
        dispatched_at: datetime,
    ) -> None:
        """Observation が runtime へ投入済みであることを記録する。"""
        ...

    async def mark_failed(
        self,
        observation_id: ObservationId,
        *,
        failed_at: datetime,
        reason: str,
    ) -> None:
        """Observation dispatch 失敗を記録する。"""
        ...


class DeliveryAvailabilityProvider(Protocol):
    """SchedulerRunner が DeliverySafetyGate へ渡す可用性を提供する port。"""

    async def availability_for_target(
        self,
        target: DeliveryTarget,
        *,
        now: datetime,
    ) -> AvailabilitySnapshot | None:
        """指定配信先の可用性スナップショットを返す。取得できない場合は None。"""
        ...
