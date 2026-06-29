"""ランタイムストアから WorkspaceFrame 用の状況コンテキストを組み立てる。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.workspace_context import SituationContextSnapshot

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from iris.contracts.observations import Observation
    from iris.runtime.state.activity_projection import ActivityProjectionStore
    from iris.runtime.state.availability import AvailabilityResolver
    from iris.runtime.state.presence import PresenceStore
    from iris.runtime.state.space_occupancy import SpaceOccupancyStore


@dataclass(frozen=True)
class WorkspaceContextAssembler:
    """ランタイムストアのスナップショットを認知 WorkspaceFrame に渡す形に組み立てる。"""

    activity_projection_store: ActivityProjectionStore | None
    presence_store: PresenceStore | None
    occupancy_store: SpaceOccupancyStore | None
    availability_resolver: AvailabilityResolver
    now: Callable[[], datetime]

    async def assemble(self, observation: Observation) -> SituationContextSnapshot:
        """観測に紐づく actor / space の状態から状況スナップショットを組み立てる。

        Args:
            observation: 処理対象の観測。

        Returns:
            SituationContextSnapshot: ランタイム状態を含む認知スナップショット。
        """
        context = observation.context
        actor_id = context.actor_id
        space_id = context.space_id

        latest_activity = None
        if actor_id is not None and self.activity_projection_store is not None:
            latest_activity = await self.activity_projection_store.latest_for_actor(actor_id)

        presence = None
        if actor_id is not None and self.presence_store is not None:
            presence = await self.presence_store.get_presence_for_actor(
                actor_id,
                now=self.now(),
            )

        space_occupancy = None
        if space_id is not None and self.occupancy_store is not None:
            space_occupancy = await self.occupancy_store.get_occupancy(
                space_id,
                now=self.now(),
            )

        availability = self.availability_resolver.derive(
            actor_id=actor_id,
            latest_activity=latest_activity,
            presence=presence,
            space_occupancy=space_occupancy,
            now=self.now(),
        )

        return SituationContextSnapshot(
            latest_activity=latest_activity,
            presence=presence,
            space_occupancy=space_occupancy,
            availability=availability,
        )
