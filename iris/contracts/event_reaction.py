"""イベント反応（event reaction）の決定と内容を表す契約。"""

from __future__ import annotations

from enum import Enum, auto

from pydantic import BaseModel, ConfigDict, Field

from iris.contracts.metadata import ImmutableMetadata
from iris.core.metadata import immutable_metadata


class EventReactionKind(Enum):
    """イベント反応のカテゴリ。"""

    GREETING = auto()
    ACKNOWLEDGMENT = auto()
    SILENT = auto()


class ReactionCandidate(BaseModel):
    """生成候補となる1つのイベント反応。"""

    model_config = ConfigDict(frozen=True)

    kind: EventReactionKind
    text: str
    reason: str
    priority: int = 0
    interruptible: bool = True
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


class EventReactionDecision(BaseModel):
    """イベント反応を行うかどうかの決定。"""

    model_config = ConfigDict(frozen=True)

    should_react: bool
    reason: str
    candidate: ReactionCandidate | None = None
