"""Memory candidate models and extractor protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from iris.core.metadata import EMPTY_METADATA

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from iris.cognitive.workspace.frame import WorkspaceFrame
    from iris.contracts.memory import MemoryKind
    from iris.core.ids import ActorId, ObservationId, SpaceId


@dataclass(frozen=True)
class MemoryCandidate:
    """保存候補となるメモリ情報。"""

    text: str
    kind: MemoryKind
    salience: float
    confidence: float
    actor_id: ActorId | None = None
    space_id: SpaceId | None = None
    source_observation_id: ObservationId | None = None
    metadata: Mapping[str, str] = EMPTY_METADATA


class MemoryCandidateExtractor(Protocol):
    """WorkspaceFrame から保存候補メモリを抽出するプロトコル。"""

    def extract(self, frame: WorkspaceFrame) -> Sequence[MemoryCandidate]:
        """フレームから保存候補を抽出する。"""
        ...
