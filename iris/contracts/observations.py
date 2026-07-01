"""外部入力イベントの型付き観測契約。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from iris.contracts.activity import ActivityKind
from iris.contracts.identity import Identity
from iris.contracts.metadata import ImmutableMetadata
from iris.contracts.presence import PresenceStatus
from iris.core.ids import (
    AccountId,
    ActionId,
    ActorId,
    DeviceId,
    ExternalRef,
    ObservationId,
    SessionId,
    SpaceId,
)
from iris.core.metadata import immutable_metadata

_ERR_BLANK_USER_FEEDBACK_TEXT = "user feedback text must not be blank"


class ObservationKind(StrEnum):
    """型付きruntime ingressが受け付ける観測の種類。"""

    ACTOR_MESSAGE = "actor_message"
    IDLE_TICK = "idle_tick"
    ACTIVITY_EVENT = "activity_event"
    PRESENCE_SIGNAL = "presence_signal"
    USER_FEEDBACK = "user_feedback"


class UserFeedbackKind(StrEnum):
    """ユーザーから届く明示的な応答品質・嗜好フィードバック種別。"""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    STYLE_PREFERENCE = "style_preference"
    CORRECTION = "correction"
    OTHER = "other"


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
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)

    @property
    def actor_id(self) -> ActorId | None:
        """actorが解決済みならactor_idを返す。"""
        return self.actor.actor_id if self.actor is not None else None


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
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


class PresenceSignalObservation(Observation):
    """外部providerが観測したactor presence signalの報告。"""

    status: PresenceStatus
    expires_at: datetime | None = None
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


class UserFeedbackObservation(Observation):
    """通常会話ではなくpost-result learningへ渡すユーザーフィードバック観測。"""

    feedback_kind: UserFeedbackKind
    text: str
    target_observation_id: ObservationId | None = None
    target_action_id: ActionId | None = None
    target_external_message_id: ExternalRef | None = None

    @field_validator("text")
    @classmethod
    def _text_must_not_be_blank(cls, value: str) -> str:
        """空白だけのfeedback textを拒否する。

        Returns:
            検証済みfeedback text。

        Raises:
            ValueError: 空白だけのfeedback textの場合。
        """
        if not value.strip():
            raise ValueError(_ERR_BLANK_USER_FEEDBACK_TEXT)
        return value
