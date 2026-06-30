"""Memory candidate models and extractor protocol."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from iris.core.metadata import EMPTY_METADATA

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from iris.cognitive.workspace.frame import WorkspaceFrame
    from iris.contracts.memory import MemoryKind
    from iris.core.ids import ActorId, ObservationId, SpaceId


class MemoryCandidateSource(StrEnum):
    """メモリ候補が生成された経路。"""

    EXPLICIT_USER_REQUEST = "explicit_user_request"
    EXPLICIT_PREFERENCE = "explicit_preference"
    IMPLICIT_CONVERSATION = "implicit_conversation"
    ACTION_RESULT = "action_result"
    REFLECTION = "reflection"
    CONSOLIDATION = "consolidation"
    LANGMEM_EXTRACTION = "langmem_extraction"
    PERSONA_PATCH = "persona_patch"


class MemoryRetentionPolicy(StrEnum):
    """候補の保存期間と審査要件。"""

    DURABLE = "durable"
    SESSION = "session"
    REVIEW_REQUIRED = "review_required"
    DISCARD_AFTER_RESTART = "discard_after_restart"
    DISCARD = "discard"


@dataclass(frozen=True)
class MemoryCandidate:
    """保存候補となるメモリ情報。"""

    text: str
    kind: MemoryKind
    salience: float
    confidence: float
    source: MemoryCandidateSource = MemoryCandidateSource.EXPLICIT_USER_REQUEST
    reason: str | None = None
    retention_policy: MemoryRetentionPolicy = MemoryRetentionPolicy.DURABLE
    review_required: bool = False
    actor_id: ActorId | None = None
    space_id: SpaceId | None = None
    source_observation_id: ObservationId | None = None
    metadata: Mapping[str, str] = EMPTY_METADATA


class MemoryCandidateExtractor(Protocol):
    """WorkspaceFrame から保存候補メモリを抽出するプロトコル。"""

    def extract(self, frame: WorkspaceFrame) -> Sequence[MemoryCandidate]:
        """フレームから保存候補を抽出する。"""
        ...
