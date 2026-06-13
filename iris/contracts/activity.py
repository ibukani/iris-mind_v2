"""外部の非message activity event契約。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from iris.core.metadata import EMPTY_METADATA, immutable_metadata

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from iris.core.ids import (
        AccountId,
        ActivityId,
        ActorId,
        DeviceId,
        ObservationId,
        SpaceId,
    )


class ActivityKind(StrEnum):
    """外部providerから届く非message activity eventの種類。"""

    ACTOR_TYPING_STARTED = "actor_typing_started"
    ACTOR_TYPING_STOPPED = "actor_typing_stopped"
    APP_OPENED = "app_opened"
    APP_CLOSED = "app_closed"
    VOICE_JOINED = "voice_joined"
    VOICE_LEFT = "voice_left"
    SYSTEM_INTERACTION = "system_interaction"


@dataclass(frozen=True)
class ActivityRecord:
    """受理済みの非message activity eventを表す内部runtime記録。"""

    activity_id: ActivityId
    observation_id: ObservationId | None
    provider_event_id: str | None
    provider_sequence: int | None
    actor_id: ActorId | None
    account_id: AccountId | None
    device_id: DeviceId | None
    space_id: SpaceId | None
    source: str | None
    kind: ActivityKind
    occurred_at: datetime
    received_at: datetime
    metadata: Mapping[str, str] = EMPTY_METADATA

    def __post_init__(self) -> None:
        """補助metadataを不変なmapping proxyとして防御的にコピーする。"""
        object.__setattr__(self, "metadata", immutable_metadata(self.metadata))
