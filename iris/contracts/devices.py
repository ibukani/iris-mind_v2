"""Device アイデンティティコンテキストの契約。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from iris.core.metadata import EMPTY_METADATA, immutable_metadata

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.core.ids import ActorId, DeviceId


class DeviceKind(StrEnum):
    """観測コンテキストを提供し得るデバイスの種類。"""

    CLIENT = "client"
    MICROPHONE = "microphone"
    SPEAKER = "speaker"
    AVATAR = "avatar"
    RUNTIME = "runtime"
    SENSOR = "sensor"


@dataclass(frozen=True)
class DeviceCapability:
    """デバイスが公開する capability。"""

    name: str
    metadata: Mapping[str, str] = EMPTY_METADATA

    def __post_init__(self) -> None:
        """メタデータを不変な mapping proxy として防御的にコピーする。"""
        object.__setattr__(self, "metadata", immutable_metadata(self.metadata))


@dataclass(frozen=True)
class DeviceProfile:
    """任意の所有 Actor にリンクされた Device プロファイル。"""

    device_id: DeviceId
    device_kind: DeviceKind
    display_name: str
    owner_actor_id: ActorId | None = None
    capabilities: tuple[DeviceCapability, ...] = ()
    metadata: Mapping[str, str] = EMPTY_METADATA

    def __post_init__(self) -> None:
        """メタデータを不変な mapping proxy として防御的にコピーする。"""
        object.__setattr__(self, "metadata", immutable_metadata(self.metadata))
