"""Device identity context contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.core.ids import ActorId, DeviceId


class DeviceKind(StrEnum):
    """Kinds of devices that may contribute observation context."""

    CLIENT = "client"
    MICROPHONE = "microphone"
    SPEAKER = "speaker"
    AVATAR = "avatar"
    RUNTIME = "runtime"
    SENSOR = "sensor"


@dataclass(frozen=True)
class DeviceCapability:
    """Capability advertised by a device."""

    name: str
    metadata: Mapping[str, str] = MappingProxyType({})


@dataclass(frozen=True)
class DeviceProfile:
    """Device profile linked to an optional owning actor."""

    device_id: DeviceId
    device_kind: DeviceKind
    display_name: str
    owner_actor_id: ActorId | None = None
    capabilities: tuple[DeviceCapability, ...] = ()
    metadata: Mapping[str, str] = MappingProxyType({})
