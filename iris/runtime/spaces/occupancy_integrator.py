"""voice activity claimのspace occupancy integration。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.activity import ActivityKind
from iris.contracts.observations import ActivityEventObservation
from iris.contracts.space_occupancy import SpaceOccupant

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from iris.contracts.observations import Observation
    from iris.runtime.observations.ingress import ObservationIngressContext
    from iris.runtime.observations.trust import ObservationTrustPolicy
    from iris.runtime.spaces.occupancy_store import SpaceOccupancyStore


@dataclass(frozen=True)
class SpaceOccupancyIntegrator:
    """trusted voice join/leave claimをSpaceOccupancyStoreへ統合する。"""

    store: SpaceOccupancyStore
    trust_policy: ObservationTrustPolicy
    now: Callable[[], datetime]

    async def integrate_observation(
        self,
        observation: Observation,
        ingress: ObservationIngressContext,
    ) -> None:
        """VOICE_JOINEDとVOICE_LEFTだけをspace occupancyへ反映する。"""
        activity = _voice_activity(observation)
        if activity is None:
            return

        context = activity.context
        trusted = self.trust_policy.can_update_space_occupancy(ingress)
        if trusted and context.actor is not None and context.space_id is not None:
            if activity.activity_kind is ActivityKind.VOICE_LEFT:
                await self.store.actor_left(
                    space_id=context.space_id,
                    actor_id=context.actor.actor_id,
                    at=activity.occurred_at,
                )
            else:
                await self.store.actor_joined(
                    space_id=context.space_id,
                    occupant=SpaceOccupant(
                        actor_id=context.actor.actor_id,
                        joined_at=activity.occurred_at,
                        last_seen_at=self.now(),
                        metadata=activity.metadata,
                    ),
                )


def _voice_activity(observation: Observation) -> ActivityEventObservation | None:
    if not isinstance(observation, ActivityEventObservation):
        return None
    if observation.activity_kind not in {
        ActivityKind.VOICE_JOINED,
        ActivityKind.VOICE_LEFT,
    }:
        return None
    return observation
