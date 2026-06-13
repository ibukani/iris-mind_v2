"""activity observation claimのruntime integration。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.activity import ActivityEventRecord
from iris.contracts.observations import ActivityEventObservation
from iris.core.ids import ActivityId

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from iris.contracts.observations import Observation
    from iris.runtime.activity.journal import ActivityJournal
    from iris.runtime.activity.projections import ActivityProjectionStore
    from iris.runtime.observations.ingress import ObservationIngressContext
    from iris.runtime.observations.trust import ObservationTrustPolicy


@dataclass(frozen=True)
class ActivityIntegrator:
    """trusted activity claimをjournalとlatest projectionへ統合する。"""

    journal: ActivityJournal
    projections: ActivityProjectionStore
    trust_policy: ObservationTrustPolicy
    now: Callable[[], datetime]

    async def integrate_observation(
        self,
        observation: Observation,
        ingress: ObservationIngressContext,
    ) -> None:
        """Trusted ActivityEventObservationだけを内部recordへ変換する。"""
        if not isinstance(observation, ActivityEventObservation):
            return
        context = observation.context
        if not self.trust_policy.can_integrate_activity_event(ingress):
            return

        actor_id = context.actor.actor_id if context.actor is not None else None
        event = ActivityEventRecord(
            activity_id=ActivityId(f"activity:{observation.observation_id}"),
            observation_id=observation.observation_id,
            provider_event_id=observation.provider_event_id,
            provider_sequence=observation.provider_sequence,
            actor_id=actor_id,
            account_id=context.account_id,
            device_id=context.device_id,
            space_id=context.space_id,
            source=context.source,
            kind=observation.activity_kind,
            occurred_at=observation.occurred_at,
            received_at=self.now(),
            metadata=observation.metadata,
        )
        result = await self.journal.append(event)
        if result.accepted and result.event is not None:
            await self.projections.update_latest(result.event)
