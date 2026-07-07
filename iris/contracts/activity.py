"""外部の非message activity event契約。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from iris.contracts.metadata import ImmutableMetadata
from iris.core.ids import (
    AccountId,
    ActivityId,
    ActorId,
    DeviceId,
    ObservationId,
    SpaceId,
)
from iris.core.metadata import immutable_metadata


class ActivityKind(StrEnum):
    """外部providerから届く非message activity eventの種類。"""

    ACTOR_TYPING_STARTED = "actor_typing_started"
    ACTOR_TYPING_STOPPED = "actor_typing_stopped"
    APP_OPENED = "app_opened"
    APP_CLOSED = "app_closed"
    VOICE_JOINED = "voice_joined"
    VOICE_LEFT = "voice_left"
    SYSTEM_INTERACTION = "system_interaction"
    ACTOR_INPUT_STARTED = "actor_input_started"
    ACTOR_INPUT_STOPPED = "actor_input_stopped"
    APP_OUTPUT_STARTED = "app_output_started"
    APP_OUTPUT_STOPPED = "app_output_stopped"


class InteractionActivityChannel(StrEnum):
    """Interaction activity projection が追跡する汎用channel。"""

    ACTOR_INPUT = "actor_input"
    APP_OUTPUT = "app_output"


class InteractionModality(StrEnum):
    """External adapter が補助情報として報告できるmodality。"""

    VOICE = "voice"
    TEXT = "text"
    VIDEO = "video"
    GESTURE = "gesture"
    NOTIFICATION = "notification"
    UNKNOWN = "unknown"


class InteractionActivitySnapshot(BaseModel):
    """認証済みingressから導出したprocess-local interaction state。"""

    model_config = ConfigDict(frozen=True)

    adapter_id: str
    provider: str | None
    actor_id: ActorId | None
    account_id: AccountId | None
    space_id: SpaceId | None
    channel: InteractionActivityChannel
    active: bool
    modality: InteractionModality
    reason: str | None
    provider_sequence: int | None
    observed_at: datetime
    received_at: datetime
    expires_at: datetime


class ActivityEventRecord(BaseModel):
    """受理済みの非message activity eventを表す内部runtime記録。"""

    model_config = ConfigDict(frozen=True)

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
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)
