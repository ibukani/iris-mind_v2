from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from iris.contracts.identity import Identity
from iris.core.ids import ExternalRef, ObservationId, SessionId


class ObservationKind(StrEnum):
    USER_MESSAGE = "user_message"
    TRANSCRIPT = "transcript"
    IDLE_TICK = "idle_tick"
    AUDIENCE_MESSAGE = "audience_message"
    GAME_EVENT = "game_event"


@dataclass(frozen=True)
class Observation:
    observation_id: ObservationId
    session_id: SessionId
    actor: Identity | None
    occurred_at: datetime
    kind: ObservationKind


@dataclass(frozen=True)
class UserMessageObservation(Observation):
    text: str
    external_message_id: ExternalRef | None = None


@dataclass(frozen=True)
class IdleTickObservation(Observation):
    reason: str | None = None
    idle_seconds: float = 0.0
