"""live interaction spaceの在室状態契約。"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from iris.core.ids import ActorId, SpaceId
from iris.core.metadata import EMPTY_METADATA, immutable_metadata


class SpaceOccupant(BaseModel):
    """live interaction spaceに在室していると判断したactor。"""

    model_config = ConfigDict(frozen=True)

    actor_id: ActorId
    joined_at: datetime
    last_seen_at: datetime
    expires_at: datetime | None = None
    metadata: Mapping[str, str] = Field(default_factory=dict)

    def model_post_init(self, __context: object) -> None:
        """補助metadataを不変なmapping proxyとして防御的にコピーする。"""
        if self.metadata is not EMPTY_METADATA:
            object.__setattr__(self, "metadata", immutable_metadata(self.metadata))


class SpaceOccupancySnapshot(BaseModel):
    """spaceごとの受理済みcurrent occupant snapshot。"""

    model_config = ConfigDict(frozen=True)

    space_id: SpaceId
    occupants: tuple[SpaceOccupant, ...]
    updated_at: datetime
