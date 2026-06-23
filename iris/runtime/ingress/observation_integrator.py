"""Observation integration protocol。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from iris.contracts.observations import Observation
    from iris.runtime.ingress.observation_ingress import ObservationIngressContext


@runtime_checkable
class ObservationIntegrator(Protocol):
    """観測をruntime stateへ統合するintegratorのstructural contract。"""

    async def integrate_observation(
        self,
        observation: Observation,
        ingress: ObservationIngressContext,
    ) -> None:
        """観測をruntime stateへ統合する。"""
        ...
