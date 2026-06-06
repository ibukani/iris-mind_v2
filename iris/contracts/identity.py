"""アクター中心のアイデンティティ契約。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from iris.core.metadata import EMPTY_METADATA, immutable_metadata

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
    provider: str | None = None
    provider_subject: ExternalRef | None = None
    account_id: AccountId | None = None
    device_id: DeviceId | None = None
    metadata: Mapping[str, str] = EMPTY_METADATA

    def __post_init__(self) -> None:
        """Defensively copy metadata as an immutable mapping proxy."""
        object.__setattr__(self, "metadata", immutable_metadata(self.metadata))
