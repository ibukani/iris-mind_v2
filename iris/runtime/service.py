"""Iris 観測のための、トランスポート非依存ランタイムサービス境界。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.actions import PresentedOutput
from iris.contracts.observations import (
    ActivityEventObservation,
    PresenceSignalObservation,
)

if TYPE_CHECKING:
    from iris.contracts.observations import Observation
    from iris.core.ids import CorrelationId
    from iris.runtime.activity.integrator import ActivityIntegrator
    from iris.runtime.app import IrisApp
    from iris.runtime.presence.integrator import PresenceIntegrator
    from iris.runtime.spaces.occupancy_integrator import SpaceOccupancyIntegrator


@dataclass(frozen=True)
class ObservationEnvelope:
    """受信観測を入れるトランスポート非依存コンテナ。"""

    observation: Observation
    correlation_id: CorrelationId | None = None


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
    ) -> None:
        """明示的に注入されたappとoptional integratorでserviceを生成する。"""
        self._app = app
        self._activity_integrator = activity_integrator
        self._presence_integrator = presence_integrator
        self._occupancy_integrator = occupancy_integrator

    async def handle_observation(self, envelope: ObservationEnvelope) -> RuntimeResponse:
        """State integration後、必要な観測だけをIrisApp経由で処理する。

        Returns:
            RuntimeResponse: PresentedOutput と保持された correlation ID。
        """
        observation = envelope.observation
        if self._activity_integrator is not None:
            await self._activity_integrator.integrate_observation(observation)
        if self._presence_integrator is not None:
            await self._presence_integrator.integrate_observation(observation)
        if self._occupancy_integrator is not None:
            await self._occupancy_integrator.integrate_observation(observation)

        if isinstance(
            observation,
            (ActivityEventObservation, PresenceSignalObservation),
        ):
            return RuntimeResponse(
                output=PresentedOutput(text=None),
                correlation_id=envelope.correlation_id,
            )

        output = await self._app.process_observation(observation)
        return RuntimeResponse(output=output, correlation_id=envelope.correlation_id)
