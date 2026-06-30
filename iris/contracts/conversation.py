"""短期会話履歴の型付き契約。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from iris.core.ids import AccountId, ActorId, ObservationId, SessionId, SpaceId


class ConversationRole(StrEnum):
    """会話メッセージの話者役割。"""

    USER = "user"
    ASSISTANT = "assistant"


class ConversationRecord(BaseModel):
    """短期会話window内の単一メッセージ。"""

    model_config = ConfigDict(frozen=True)

    role: ConversationRole
    content: str
    occurred_at: datetime
    observation_id: ObservationId | None
    session_id: SessionId
    actor_id: ActorId | None = None
    account_id: AccountId | None = None
    space_id: SpaceId | None = None


class ConversationWindow(BaseModel):
    """時系列順の短期会話メッセージ集合。"""

    model_config = ConfigDict(frozen=True)

    records: tuple[ConversationRecord, ...] = ()
