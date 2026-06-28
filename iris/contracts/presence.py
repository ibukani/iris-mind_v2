"""外部providerから見えるactor presence契約。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from iris.contracts.metadata import ImmutableMetadata
from iris.core.ids import AccountId, ActorId, DeviceId
from iris.core.metadata import immutable_metadata


class PresenceStatus(StrEnum):
    """外部providerから見えるactorのpresence状態。"""

    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"
    AWAY = "away"
    IDLE = "idle"
    DO_NOT_DISTURB = "do_not_disturb"
    INVISIBLE = "invisible"


class PresenceSnapshot(BaseModel):
    """受理済みprovider-visible actor presenceの内部snapshot。"""

    model_config = ConfigDict(frozen=True)

    actor_id: ActorId | None
    account_id: AccountId | None
    device_id: DeviceId | None
    source: str | None
    status: PresenceStatus
    observed_at: datetime
    received_at: datetime
    expires_at: datetime | None = None
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)
