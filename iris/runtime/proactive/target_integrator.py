"""Ingress delivery route hints を proactive target store へ統合する。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from iris.runtime.observations.ingress import ObservationCapability, ObservationIngressContext
from iris.runtime.observations.integrator import ObservationIntegrator
from iris.runtime.proactive.targets import ProactiveTarget, ProactiveTargetStore

if TYPE_CHECKING:
    from iris.contracts.observations import Observation


@dataclass(frozen=True)
class ProactiveTargetIntegrator(ObservationIntegrator):
    """Trusted ingress route hint から proactive target を登録する integrator。"""

    target_store: ProactiveTargetStore

    @override
    async def integrate_observation(
        self,
        observation: Observation,
        ingress: ObservationIngressContext,
    ) -> None:
        """Capability と route hint がある ingress だけ target 登録する。"""
        if not ingress.authenticated:
            return
        if ObservationCapability.REGISTER_DELIVERY_TARGET not in ingress.capabilities:
            return
        if ingress.delivery_route is None:
            return
        context = observation.context
        target = ProactiveTarget(
            actor_id=context.actor_id,
            account_id=context.account_id,
            space_id=context.space_id,
            session_id=observation.session_id,
            route=ingress.delivery_route,
            display_name=ingress.delivery_route.display_name,
            last_observed_at=observation.occurred_at,
        )
        await self.target_store.upsert_target(target)
