"""イベント反応（event reaction）の決定と内容を表す契約。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

from iris.core.metadata import EMPTY_METADATA, immutable_metadata

if TYPE_CHECKING:
    from collections.abc import Mapping


class EventReactionKind(Enum):
    """イベント反応のカテゴリ。"""

    GREETING = auto()
    ACKNOWLEDGMENT = auto()
    SILENT = auto()


@dataclass(frozen=True)
class ReactionCandidate:
    """生成候補となる1つのイベント反応。"""

    kind: EventReactionKind
    text: str
    reason: str
    priority: int = 0
    interruptible: bool = True
    metadata: Mapping[str, str] = EMPTY_METADATA

    def __post_init__(self) -> None:
        """補助metadataを不変なmapping proxyとして防御的にコピーする。"""
        object.__setattr__(self, "metadata", immutable_metadata(self.metadata))


@dataclass(frozen=True)
class EventReactionDecision:
    """イベント反応を行うかどうかの決定。"""

    should_react: bool
    reason: str
    candidate: ReactionCandidate | None = None
