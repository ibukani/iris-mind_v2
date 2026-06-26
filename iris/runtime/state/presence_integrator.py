"""presence observation claimのruntime integration。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.presence import PresenceSnapshot
from iris.runtime.observation_router import presence_signal_observation

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from iris.contracts.observations import Observation
    from iris.runtime.ingress.observation_ingress import ObservationIngressContext
    from iris.runtime.ingress.observation_trust import ObservationTrustPolicy
    from iris.runtime.state.presence import PresenceStore


@dataclass(frozen=True)
class PresenceIntegrator:
    """trusted presence claimをPresenceStoreへ統合する。"""

    store: PresenceStore
    trust_policy: ObservationTrustPolicy
    now: Callable[[], datetime]

    async def integrate_observation(
        self,
        observation: Observation,
        ingress: ObservationIngressContext,
    ) -> None:
        """Resolved actorを持つtrusted PresenceSignalObservationだけを統合する。"""
        presence = presence_signal_observation(observation)
        if presence is None:
            return
        context = presence.context
        if not self.trust_policy.can_integrate_presence_signal(ingress):
            return
        if context.actor is None:
            return

        await self.store.update_presence(
            PresenceSnapshot(
                actor_id=context.actor.actor_id,
                account_id=context.account_id,
                device_id=context.device_id,
                source=context.source,
                status=presence.status,
                observed_at=presence.occurred_at,
                received_at=self.now(),
                expires_at=presence.expires_at,
                metadata=presence.metadata,
            )
        )
