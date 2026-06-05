"""Transport-neutral runtime service boundary for Iris observations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.contracts.actions import PresentedOutput
    from iris.contracts.observations import Observation
    from iris.core.ids import CorrelationId
    from iris.runtime.app import IrisApp


@dataclass(frozen=True)
class ObservationEnvelope:
    """Transport-neutral container for an incoming observation."""

    observation: Observation
    correlation_id: CorrelationId | None = None


@dataclass(frozen=True)
class RuntimeResponse:
    """Transport-neutral result returned by IrisRuntimeService."""

    output: PresentedOutput
    correlation_id: CorrelationId | None = None


class IrisRuntimeService:
    """Thin runtime service that delegates observations to IrisApp."""

    def __init__(self, app: IrisApp) -> None:
        """Create service with an explicitly injected IrisApp."""
        self._app = app

    async def handle_observation(self, envelope: ObservationEnvelope) -> RuntimeResponse:
        """Process an observation envelope through IrisApp.

        Returns:
            RuntimeResponse: PresentedOutput plus preserved correlation ID.
        """
        output = await self._app.process_observation(envelope.observation)
        return RuntimeResponse(output=output, correlation_id=envelope.correlation_id)
