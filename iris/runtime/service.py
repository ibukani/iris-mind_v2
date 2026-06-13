"""Iris 観測のための、トランスポート非依存ランタイムサービス境界。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.actions import PresentedOutput
from iris.contracts.observations import (
    ActivityEventObservation,
    PresenceSignalObservation,
)
from iris.runtime.observations.ingress import unauthenticated_external_ingress

if TYPE_CHECKING:
    from iris.contracts.observations import Observation
    from iris.core.ids import CorrelationId
    from iris.runtime.activity.integrator import ActivityIntegrator
    from iris.runtime.app import IrisApp
    from iris.runtime.context.workspace_assembler import WorkspaceContextAssembler
    from iris.runtime.observations.ingress import ObservationIngressContext
    from iris.runtime.presence.integrator import PresenceIntegrator
    from iris.runtime.spaces.occupancy_integrator import SpaceOccupancyIntegrator


@dataclass(frozen=True)
class ObservationEnvelope:
    """受信観測を入れるトランスポート非依存コンテナ。"""

    observation: Observation
    ingress: ObservationIngressContext
    correlation_id: CorrelationId | None = None

    @classmethod
    def external_client(
        cls,
        *,
        observation: Observation,
        correlation_id: CorrelationId | None = None,
    ) -> ObservationEnvelope:
        """外部client request用のcapabilityなしenvelopeを作成する。

        Returns:
            未認証ingressを持つObservationEnvelope。
        """
        return cls(
            observation=observation,
            ingress=unauthenticated_external_ingress(),
            correlation_id=correlation_id,
        )


@dataclass(frozen=True)
class RuntimeResponse:
    """IrisRuntimeService が返すトランスポート非依存の結果。"""

    output: PresentedOutput
    correlation_id: CorrelationId | None = None


class IrisRuntimeService:
    """観測stateを統合し、sendable観測だけをIrisAppへ委譲するruntime境界。"""

    def __init__(
        self,
        app: IrisApp,
        *,
        activity_integrator: ActivityIntegrator | None = None,
        presence_integrator: PresenceIntegrator | None = None,
        occupancy_integrator: SpaceOccupancyIntegrator | None = None,
        workspace_context_assembler: WorkspaceContextAssembler | None = None,
    ) -> None:
        """明示的に注入されたappとoptional integratorでserviceを生成する。"""
        self._app = app
        self._activity_integrator = activity_integrator
        self._presence_integrator = presence_integrator
        self._occupancy_integrator = occupancy_integrator
        self._workspace_context_assembler = workspace_context_assembler

    async def handle_observation(self, envelope: ObservationEnvelope) -> RuntimeResponse:
        """State integration後、必要な観測だけをIrisApp経由で処理する。

        Returns:
            RuntimeResponse: PresentedOutput と保持された correlation ID。
        """
        observation = envelope.observation
        if self._activity_integrator is not None:
            await self._activity_integrator.integrate_observation(
                observation,
                envelope.ingress,
            )
        if self._presence_integrator is not None:
            await self._presence_integrator.integrate_observation(
                observation,
                envelope.ingress,
            )
        if self._occupancy_integrator is not None:
            await self._occupancy_integrator.integrate_observation(
                observation,
                envelope.ingress,
            )

        if isinstance(
            observation,
            (ActivityEventObservation, PresenceSignalObservation),
        ):
            return RuntimeResponse(
                output=PresentedOutput(text=None),
                correlation_id=envelope.correlation_id,
            )

        situation_context = None
        if self._workspace_context_assembler is not None:
            situation_context = await self._workspace_context_assembler.assemble(observation)

        output = await self._app.process_observation(
            observation,
            situation_context=situation_context,
        )
        return RuntimeResponse(output=output, correlation_id=envelope.correlation_id)
