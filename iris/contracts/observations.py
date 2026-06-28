"""外部入力イベントの型付き観測契約。"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from iris.contracts.activity import ActivityKind
from iris.contracts.identity import Identity
from iris.contracts.presence import PresenceStatus
from iris.core.ids import (
    AccountId,
    ActorId,
    DeviceId,
    ExternalRef,
    ObservationId,
    SessionId,
    SpaceId,
)
from iris.core.metadata import EMPTY_METADATA, immutable_metadata


class ObservationKind(StrEnum):
    """型付きruntime ingressが受け付ける観測の種類。"""

    ACTOR_MESSAGE = "actor_message"
    IDLE_TICK = "idle_tick"
    ACTIVITY_EVENT = "activity_event"
    PRESENCE_SIGNAL = "presence_signal"


class ObservationContext(BaseModel):
    """観測に紐づく actor/account/device/space context。

    sourceはtransport/adapter報告のaudit/debug labelに限る。trust判定には
    runtime-owned ObservationIngressContext を使う。
    """

    model_config = ConfigDict(frozen=True)

    actor: Identity | None = None
    account_id: AccountId | None = None
    device_id: DeviceId | None = None
    space_id: SpaceId | None = None
    source: str | None = None
    metadata: Mapping[str, str] = Field(default_factory=dict)

    @property
    def actor_id(self) -> ActorId | None:
        """actorが解決済みならactor_idを返す。"""
        return self.actor.actor_id if self.actor is not None else None

    def model_post_init(self, __context: object) -> None:
        """メタデータを不変な mapping proxy として防御的にコピーする。"""
        if self.metadata is not EMPTY_METADATA:
            object.__setattr__(self, "metadata", immutable_metadata(self.metadata))


class Observation(BaseModel):
    """認知runtimeへ入る基底観測。"""

    model_config = ConfigDict(frozen=True)

    observation_id: ObservationId
    session_id: SessionId
    context: ObservationContext
    occurred_at: datetime
    kind: ObservationKind


class ActorMessageObservation(Observation):
    """Actorから届いたテキストmessage観測。"""

    text: str
    external_message_id: ExternalRef | None = None


class IdleTickObservation(Observation):
    """Proactive処理などの内部idle tick観測。"""

    reason: str | None = None
    idle_seconds: float = 0.0


class ActivityEventObservation(Observation):
    """外部providerから届いた非message activity event観測。"""

    activity_kind: ActivityKind
    provider_event_id: str | None = None
    provider_sequence: int | None = None
    metadata: Mapping[str, str] = Field(default_factory=dict)

    def model_post_init(self, __context: object) -> None:
        """補助metadataを不変なmapping proxyとして防御的にコピーする。"""
        if self.metadata is not EMPTY_METADATA:
            object.__setattr__(self, "metadata", immutable_metadata(self.metadata))


class PresenceSignalObservation(Observation):
    """外部providerが観測したactor presence signalの報告。"""

    status: PresenceStatus
    expires_at: datetime | None = None
    metadata: Mapping[str, str] = Field(default_factory=dict)

    def model_post_init(self, __context: object) -> None:
        """補助metadataを不変なmapping proxyとして防御的にコピーする。"""
        if self.metadata is not EMPTY_METADATA:
            object.__setattr__(self, "metadata", immutable_metadata(self.metadata))
