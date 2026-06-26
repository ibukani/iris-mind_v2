"""相互作用スペースの型付き契約。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from iris.core.metadata import EMPTY_METADATA, immutable_metadata

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.core.ids import SpaceId


class SpaceKind(StrEnum):
    """相互作用スペースの種類。"""

    DIRECT_MESSAGE = "direct_message"
    TEXT_CHANNEL = "text_channel"
    THREAD = "thread"
    VOICE_CHANNEL = "voice_channel"
    ROOM = "room"
    BROADCAST = "broadcast"


@dataclass(frozen=True)
class InteractionSpace:
    """観察された相互作用スペースの安定した識別情報とコンテキスト。

    現在の在室者は保持しない。SpaceOccupancyStore が在室者情報の正本を担う。
    """

    space_id: SpaceId
    space_kind: SpaceKind
    display_name: str
    metadata: Mapping[str, str] = EMPTY_METADATA

    def __post_init__(self) -> None:
        """メタデータが強固に不変であることを保証する。"""
        object.__setattr__(self, "metadata", immutable_metadata(self.metadata))
