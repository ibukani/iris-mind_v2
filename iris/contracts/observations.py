"""外部入力イベントの型付き観測契約。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from iris.contracts.identity import Identity
    from iris.core.ids import (
        AccountId,
        DeviceId,
        ExternalRef,
        ObservationId,
        SessionId,
        SpaceId,
    )


class ObservationKind(StrEnum):
    """観測の種類。"""

    ACTOR_MESSAGE = "actor_message"
    TRANSCRIPT = "transcript"
    IDLE_TICK = "idle_tick"
    AUDIENCE_MESSAGE = "audience_message"
    GAME_EVENT = "game_event"


@dataclass(frozen=True)
class ObservationContext:
    """観測に紐づく actor/account/device/space context。"""

    actor: Identity | None = None
    account_id: AccountId | None = None
    device_id: DeviceId | None = None
    space_id: SpaceId | None = None
    source: str | None = None


@dataclass(frozen=True)
class Observation:
    """認知runtimeへ入る基底観測。"""

    observation_id: ObservationId
    session_id: SessionId
    context: ObservationContext
    occurred_at: datetime
    kind: ObservationKind


@dataclass(frozen=True)
class ActorMessageObservation(Observation):
    """Actorから届いたテキストmessage観測。"""

    text: str
    external_message_id: ExternalRef | None = None


@dataclass(frozen=True)
class IdleTickObservation(Observation):
    """Proactive処理などの内部idle tick観測。"""

    reason: str | None = None
    idle_seconds: float = 0.0
