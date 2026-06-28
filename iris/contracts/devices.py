"""Device アイデンティティコンテキストの契約。"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from iris.core.ids import ActorId, DeviceId
from iris.core.metadata import EMPTY_METADATA, immutable_metadata


class DeviceKind(StrEnum):
    """観測コンテキストを提供し得るデバイスの種類。"""

    CLIENT = "client"
    MICROPHONE = "microphone"
    SPEAKER = "speaker"
    AVATAR = "avatar"
    RUNTIME = "runtime"
    SENSOR = "sensor"


class DeviceCapability(BaseModel):
    """デバイスが公開する capability。"""

    model_config = ConfigDict(frozen=True)

    name: str
    metadata: Mapping[str, str] = Field(default_factory=dict)

    def model_post_init(self, __context: object) -> None:
        """メタデータを不変な mapping proxy として防御的にコピーする。"""
        if self.metadata is not EMPTY_METADATA:
            object.__setattr__(self, "metadata", immutable_metadata(self.metadata))


class DeviceProfile(BaseModel):
    """任意の所有 Actor にリンクされた Device プロファイル。"""

    model_config = ConfigDict(frozen=True)

    device_id: DeviceId
    device_kind: DeviceKind
    display_name: str
    owner_actor_id: ActorId | None = None
    capabilities: tuple[DeviceCapability, ...] = ()
    metadata: Mapping[str, str] = Field(default_factory=dict)

    def model_post_init(self, __context: object) -> None:
        """メタデータを不変な mapping proxy として防御的にコピーする。"""
        if self.metadata is not EMPTY_METADATA:
            object.__setattr__(self, "metadata", immutable_metadata(self.metadata))
