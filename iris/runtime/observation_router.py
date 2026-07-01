"""Observation の種類別処理先を決める runtime 専用 router。"""

from __future__ import annotations

from dataclasses import dataclass

from iris.contracts.observations import (
    ActivityEventObservation,
    ActorMessageObservation,
    Observation,
    PresenceSignalObservation,
    UserFeedbackObservation,
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
class UserFeedbackRoute:
    """UserFeedbackObservation を認知cycleへ流さず学習境界へ渡す route。"""

    observation: UserFeedbackObservation


@dataclass(frozen=True)
class CognitiveRoute:
    """通常の cognitive cycle へ渡す route。"""

    observation: Observation


type ObservationRoute = (
    ActivityEventRoute | PresenceSignalRoute | UserFeedbackRoute | CognitiveRoute
)


def route_observation(observation: Observation) -> ObservationRoute:
    """Observation を runtime の後続処理 route へ分類する。

    Returns:
        Observation route。
    """
    if isinstance(observation, ActivityEventObservation):
        return ActivityEventRoute(observation)
    if isinstance(observation, PresenceSignalObservation):
        return PresenceSignalRoute(observation)
    if isinstance(observation, UserFeedbackObservation):
        return UserFeedbackRoute(observation)
    return CognitiveRoute(observation)


def activity_event_observation(
    observation: Observation,
) -> ActivityEventObservation | None:
    """ActivityEventObservation なら typed observation を返す。

    Returns:
        ActivityEventObservation または None。
    """
    if isinstance(observation, ActivityEventObservation):
        return observation
    return None


def presence_signal_observation(
    observation: Observation,
) -> PresenceSignalObservation | None:
    """PresenceSignalObservation なら typed observation を返す。

    Returns:
        PresenceSignalObservation または None。
    """
    if isinstance(observation, PresenceSignalObservation):
        return observation
    return None


def user_feedback_observation(
    observation: Observation,
) -> UserFeedbackObservation | None:
    """UserFeedbackObservation なら typed observation を返す。

    Returns:
        UserFeedbackObservation または None。
    """
    if isinstance(observation, UserFeedbackObservation):
        return observation
    return None


def actor_message_observation(
    observation: Observation,
) -> ActorMessageObservation | None:
    """ActorMessageObservationならtyped observationを返す。

    Returns:
        ActorMessageObservationまたはNone。
    """
    if isinstance(observation, ActorMessageObservation):
        return observation
    return None
