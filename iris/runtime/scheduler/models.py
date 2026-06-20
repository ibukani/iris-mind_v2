"""Scheduler shared models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.contracts.delivery import DeliveryTarget
    from iris.contracts.observations import Observation
    from iris.core.ids import CorrelationId


@dataclass(frozen=True)
class ScheduledObservation:
    """RuntimeScheduler が due と判断した typed observation。"""

    observation: Observation
    correlation_id: CorrelationId | None
    reason: str
    target: DeliveryTarget | None = None
