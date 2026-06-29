"""アクター中心のアイデンティティ契約。"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from iris.contracts.metadata import ImmutableMetadata
from iris.core.ids import AccountId, ActorId, DeviceId, ExternalRef
from iris.core.metadata import immutable_metadata


class ActorKind(StrEnum):
    """アクターの種類。"""

    HUMAN = "human"
    DEVICE = "device"
    SERVICE = "service"
    SYSTEM = "system"
    IRIS = "iris"


class Identity(BaseModel):
    """アクター中心のアイデンティティ表現。"""

    model_config = ConfigDict(frozen=True)

    actor_id: ActorId
    actor_kind: ActorKind
    display_name: str
    provider: str | None = None
    provider_subject: ExternalRef | None = None
    account_id: AccountId | None = None
    device_id: DeviceId | None = None
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)
