"""activity observation claimのruntime integration。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.activity import ActivityEventRecord
from iris.core.ids import ActivityId
from iris.runtime.observation_router import activity_event_observation

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from iris.contracts.observations import Observation
    from iris.runtime.ingress.observation_ingress import ObservationIngressContext
    from iris.runtime.ingress.observation_trust import ObservationTrustPolicy
    from iris.runtime.state.activity_journal import ActivityJournal
    from iris.runtime.state.activity_projection import ActivityProjectionStore


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
        activity = activity_event_observation(observation)
        if activity is None:
            return
        context = activity.context
        if not self.trust_policy.can_integrate_activity_event(ingress):
            return

        event = ActivityEventRecord(
            activity_id=ActivityId(f"activity:{activity.observation_id}"),
            observation_id=activity.observation_id,
            provider_event_id=activity.provider_event_id,
            provider_sequence=activity.provider_sequence,
            actor_id=context.actor_id,
            account_id=context.account_id,
            device_id=context.device_id,
            space_id=context.space_id,
            source=context.source,
            kind=activity.activity_kind,
            occurred_at=activity.occurred_at,
            received_at=self.now(),
            metadata=activity.metadata,
        )
        result = await self.journal.append(event)
        if result.accepted and result.event is not None:
            await self.projections.update_latest(result.event)
