"""live interaction spaceの在室状態契約。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.core.metadata import EMPTY_METADATA, immutable_metadata

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from iris.core.ids import ActorId, SpaceId


@dataclass(frozen=True)
class SpaceOccupant:
    """live interaction spaceに在室していると判断したactor。"""

    actor_id: ActorId
    joined_at: datetime
    last_seen_at: datetime
    expires_at: datetime | None = None
    metadata: Mapping[str, str] = EMPTY_METADATA

    def __post_init__(self) -> None:
        """補助metadataを不変なmapping proxyとして防御的にコピーする。"""
        object.__setattr__(self, "metadata", immutable_metadata(self.metadata))


@dataclass(frozen=True)
class SpaceOccupancySnapshot:
    """spaceごとの受理済みcurrent occupant snapshot。"""

    space_id: SpaceId
    occupants: tuple[SpaceOccupant, ...]
    updated_at: datetime
