"""live interaction spaceの在室状態契約。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from iris.contracts.metadata import ImmutableMetadata
from iris.core.ids import ActorId, SpaceId
from iris.core.metadata import immutable_metadata


class SpaceOccupant(BaseModel):
    """live interaction spaceに在室していると判断したactor。"""

    model_config = ConfigDict(frozen=True)

    actor_id: ActorId
    joined_at: datetime
    last_seen_at: datetime
    expires_at: datetime | None = None
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


class SpaceOccupancySnapshot(BaseModel):
    """spaceごとの受理済みcurrent occupant snapshot。"""

    model_config = ConfigDict(frozen=True)

    space_id: SpaceId
    occupants: tuple[SpaceOccupant, ...]
    updated_at: datetime
