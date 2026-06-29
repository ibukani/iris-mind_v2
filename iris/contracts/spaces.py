"""相互作用スペースの型付き契約。"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from iris.contracts.metadata import ImmutableMetadata
from iris.core.ids import SpaceId
from iris.core.metadata import immutable_metadata


class SpaceKind(StrEnum):
    """相互作用スペースの種類。"""

    DIRECT_MESSAGE = "direct_message"
    TEXT_CHANNEL = "text_channel"
    THREAD = "thread"
    VOICE_CHANNEL = "voice_channel"
    ROOM = "room"
    BROADCAST = "broadcast"


class InteractionSpace(BaseModel):
    """観察された相互作用スペースの安定した識別情報とコンテキスト。

    現在の在室者は保持しない。SpaceOccupancyStore が在室者情報の正本を担う。
    """

    model_config = ConfigDict(frozen=True)

    space_id: SpaceId
    space_kind: SpaceKind
    display_name: str
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)
