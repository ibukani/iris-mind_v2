"""メモリ保存・検索の型付き契約。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, NewType

from iris.core.metadata import EMPTY_METADATA, immutable_metadata

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from iris.core.ids import ActorId, ObservationId, SpaceId

MemoryId = NewType("MemoryId", str)


class MemoryKind(StrEnum):
    """メモリレコードの種別。"""

    EPISODE = "episode"
    PREFERENCE = "preference"
    FACT = "fact"
    RELATIONSHIP = "relationship"
    TASK = "task"
    NOTE = "note"


@dataclass(frozen=True)
class MemoryRecord:
    """単一のメモリレコード。"""

    id: MemoryId
    text: str
    actor_id: ActorId | None = None
    space_id: SpaceId | None = None
    salience: float = 0.0
    kind: MemoryKind = MemoryKind.NOTE
    confidence: float = 1.0
    source_observation_id: ObservationId | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    archived: bool = False
    metadata: Mapping[str, str] = EMPTY_METADATA

    def __post_init__(self) -> None:
        """メタデータを不変な mapping proxy として防御的にコピーする。"""
        object.__setattr__(self, "metadata", immutable_metadata(self.metadata))


@dataclass(frozen=True)
class MemoryQuery:
    """メモリレコード検索のクエリ。"""

    text: str
    actor_id: ActorId | None = None
    space_id: SpaceId | None = None
    limit: int = 5
    kind: MemoryKind | None = None
    include_archived: bool = False


@dataclass(frozen=True)
class MemorySearchResult:
    """関連性スコア付きのメモリレコード。"""

    record: MemoryRecord
    score: float
