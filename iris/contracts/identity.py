"""アクター中心のアイデンティティ契約。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.core.ids import AccountId, ActorId, DeviceId, ExternalRef


class ActorKind(StrEnum):
    """アクターの種類。"""

    HUMAN = "human"
    DEVICE = "device"
    SERVICE = "service"
    SYSTEM = "system"
    IRIS = "iris"


@dataclass(frozen=True)
class Identity:
    """アクター中心のアイデンティティ表現。"""

    actor_id: ActorId
    actor_kind: ActorKind
    display_name: str
    provider: str
    provider_subject: ExternalRef
    account_id: AccountId | None = None
    device_id: DeviceId | None = None
    metadata: Mapping[str, str] = MappingProxyType({})
