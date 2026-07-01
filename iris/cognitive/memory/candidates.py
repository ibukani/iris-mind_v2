"""Memory candidate extractor protocol と cognitive re-export。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from iris.contracts.memory_candidates import (
    MemoryCandidate,
    MemoryCandidateSensitivity,
    MemoryCandidateSource,
    MemoryRetentionPolicy,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.cognitive.workspace.frame import WorkspaceFrame


class MemoryCandidateExtractor(Protocol):
    """WorkspaceFrame から保存候補メモリを抽出するプロトコル。"""

    def extract(self, frame: WorkspaceFrame) -> Sequence[MemoryCandidate]:
        """フレームから保存候補を抽出する。"""
        ...


__all__ = [
    "MemoryCandidate",
    "MemoryCandidateExtractor",
    "MemoryCandidateSensitivity",
    "MemoryCandidateSource",
    "MemoryRetentionPolicy",
]
