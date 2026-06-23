"""DeliveryAvailabilityProvider adapter for SchedulerRunner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from iris.contracts.availability import AvailabilitySnapshot
    from iris.contracts.delivery import DeliveryTarget
    from iris.runtime.state.activity_projection import ActivityProjectionStore
    from iris.runtime.state.availability import AvailabilityResolver
    from iris.runtime.state.presence import PresenceStore


@dataclass(frozen=True)
class DeliveryAvailabilityResolverAdapter:
    """DeliveryAvailabilityProvider backed by runtime presence and activity stores.

    target.actor_id が None の場合は可用性を解決できないため None を返す。
    それ以外は PresenceStore / ActivityProjectionStore からスナップショットを
    取得し、AvailabilityResolver で AvailabilitySnapshot を導出する。
    """

    resolver: AvailabilityResolver
    presence_store: PresenceStore
    activity_projection_store: ActivityProjectionStore

    async def availability_for_target(
        self,
        target: DeliveryTarget,
        *,
        now: datetime,
    ) -> AvailabilitySnapshot | None:
        """配信先の可用性スナップショットを返す。

        Returns:
            AvailabilitySnapshot: 導出結果。target.actor_id が None の場合は None。
        """
        actor_id = target.actor_id
        if actor_id is None:
            return None
        presence = await self.presence_store.get_presence_for_actor(actor_id, now=now)
        latest_activity = await self.activity_projection_store.latest_for_actor(actor_id)
        return self.resolver.derive(
            actor_id=actor_id,
            latest_activity=latest_activity,
            presence=presence,
            space_occupancy=None,
            now=now,
        )
