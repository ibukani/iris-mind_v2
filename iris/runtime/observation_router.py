"""Observation の種類別処理先を決める runtime 専用 router。"""

from __future__ import annotations

from dataclasses import dataclass

from iris.contracts.observations import (
    ActivityEventObservation,
    Observation,
    PresenceSignalObservation,
)


@dataclass(frozen=True)
class ActivityEventRoute:
    """ActivityEventObservation を event reaction handler へ渡す route。"""

    observation: ActivityEventObservation


@dataclass(frozen=True)
class PresenceSignalRoute:
    """PresenceSignalObservation を cognitive cycle へ流さず no-send にする route。"""

    observation: PresenceSignalObservation


@dataclass(frozen=True)
class CognitiveRoute:
    """通常の cognitive cycle へ渡す route。"""

    observation: Observation


type ObservationRoute = ActivityEventRoute | PresenceSignalRoute | CognitiveRoute


def route_observation(observation: Observation) -> ObservationRoute:
    """Observation を runtime の後続処理 route へ分類する。

    Returns:
        Observation route。
    """
    if isinstance(observation, ActivityEventObservation):
        return ActivityEventRoute(observation)
    if isinstance(observation, PresenceSignalObservation):
        return PresenceSignalRoute(observation)
    return CognitiveRoute(observation)
