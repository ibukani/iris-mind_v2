"""外部providerから見えるactor presence契約。"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from iris.core.ids import AccountId, ActorId, DeviceId
from iris.core.metadata import EMPTY_METADATA, immutable_metadata


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
    metadata: Mapping[str, str] = Field(default_factory=dict)

    def model_post_init(self, __context: object) -> None:
        """補助metadataを不変なmapping proxyとして防御的にコピーする。"""
        if self.metadata is not EMPTY_METADATA:
            object.__setattr__(self, "metadata", immutable_metadata(self.metadata))
