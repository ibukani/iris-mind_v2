"""外部入力イベントの型付き観測契約。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from iris.contracts.identity import Identity
    from iris.core.ids import ExternalRef, ObservationId, SessionId, SpaceId


class ObservationKind(StrEnum):
    """観測の種類。"""

    USER_MESSAGE = "user_message"
    TRANSCRIPT = "transcript"
    IDLE_TICK = "idle_tick"
    AUDIENCE_MESSAGE = "audience_message"
    GAME_EVENT = "game_event"


@dataclass(frozen=True)
class Observation:
    """外部イベントを表す基底観測。"""

    observation_id: ObservationId
    session_id: SessionId
    actor: Identity | None
    space_id: SpaceId | None
    occurred_at: datetime
    kind: ObservationKind


@dataclass(frozen=True)
class UserMessageObservation(Observation):
    """直接ユーザーメッセージの観測。"""

    text: str
    external_message_id: ExternalRef | None = None


@dataclass(frozen=True)
class IdleTickObservation(Observation):
    """プロアクティブ動作をトリガーするためのアイドルティック観測。"""

    reason: str | None = None
    idle_seconds: float = 0.0
