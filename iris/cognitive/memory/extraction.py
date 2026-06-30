"""Rule-based memory candidate extraction from interpreted input text."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, override

from iris.cognitive.memory.candidates import (
    MemoryCandidate,
    MemoryCandidateExtractor,
    MemoryCandidateSource,
    MemoryRetentionPolicy,
)
from iris.contracts.memory import MemoryKind

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.cognitive.workspace.frame import WorkspaceFrame
    from iris.core.ids import ActorId, ObservationId, SpaceId

_REMEMBER_PATTERNS = (
    r"覚えて[:\uff1a]\s*(.+)",
    r"覚えておいて[:\uff1a]\s*(.+)",
    r"remember[:\uff1a]\s*(.+)",
    r"remember that\s+(.+)",
)

_PREFERENCE_PATTERNS = (
    r"私は(.+)が好き",
    r"私は(.+)を好む",
    r"I (?:like|love|prefer)\s+(.+)[\.。]?",
    r"I (?:dislike|hate)\s+(.+)[\.。]?",
    r"今後(.+?)してほしい",
    r"Please\s+(.+?)\s+from now on",
    r"I want you to\s+(.+)[\.。]?",
    r"(.+?)は日本語で書いてほしい",
    r"(.+?)を日本語で",
    r"Write\s+(.+?)\s+in Japanese",
)

_SKIP_PATTERNS = (
    r"保存しないで",
    r"don't save",
    r"覚えなくていい",
    r"no need to remember",
)


class RuleBasedMemoryCandidateExtractor(MemoryCandidateExtractor):
    """キーワードパターンで MemoryCandidate を抽出する rule-based 抽出器。"""

    @override
    def extract(self, frame: WorkspaceFrame) -> Sequence[MemoryCandidate]:
        """フレームの解釈済み入力から保存候補を抽出する。

        Returns:
            Sequence[MemoryCandidate]: 抽出された候補のシーケンス。
        """
        if frame.interpreted_input is None or not frame.interpreted_input.text:
            return ()

        text = frame.interpreted_input.text
        actor = frame.actor_context.actor
        actor_id: ActorId | None = actor.actor_id if actor is not None else None
        space_id: SpaceId | None = frame.space_context.space_id
        source_observation_id: ObservationId = frame.observation.observation_id

        if any(re.search(pattern, text, re.IGNORECASE) for pattern in _SKIP_PATTERNS):
            return ()

        candidates: list[MemoryCandidate] = []
        candidates.extend(_extract_remember(text, actor_id, space_id, source_observation_id))
        candidates.extend(_extract_preferences(text, actor_id, space_id, source_observation_id))
        return tuple(candidates)


def _extract_remember(
    text: str,
    actor_id: ActorId | None,
    space_id: SpaceId | None,
    source_observation_id: ObservationId,
) -> list[MemoryCandidate]:
    """覚えて/remember パターンから候補を抽出する。

    Returns:
        list[MemoryCandidate]: 抽出された候補リスト。
    """
    candidates: list[MemoryCandidate] = []
    for pattern in _REMEMBER_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            raw_group = match.group(1)
            if not isinstance(raw_group, str):
                continue
            content = raw_group.strip()
            if content:
                candidates.append(
                    MemoryCandidate(
                        text=content,
                        kind=MemoryKind.NOTE,
                        salience=0.8,
                        confidence=0.9,
                        source=MemoryCandidateSource.EXPLICIT_USER_REQUEST,
                        reason="user explicitly requested durable memory",
                        retention_policy=MemoryRetentionPolicy.DURABLE,
                        review_required=False,
                        actor_id=actor_id,
                        space_id=space_id,
                        source_observation_id=source_observation_id,
                    )
                )
    return candidates


def _extract_preferences(
    text: str,
    actor_id: ActorId | None,
    space_id: SpaceId | None,
    source_observation_id: ObservationId,
) -> list[MemoryCandidate]:
    """好み/方針パターンから候補を抽出する。

    Returns:
        list[MemoryCandidate]: 抽出された候補リスト。
    """
    candidates: list[MemoryCandidate] = []
    for pattern in _PREFERENCE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            raw_group = match.group(1)
            if not isinstance(raw_group, str):
                continue
            content = raw_group.strip()
            if content:
                candidates.append(
                    MemoryCandidate(
                        text=content,
                        kind=MemoryKind.PREFERENCE,
                        salience=0.7,
                        confidence=0.85,
                        source=MemoryCandidateSource.EXPLICIT_PREFERENCE,
                        reason="user stated an explicit preference",
                        retention_policy=MemoryRetentionPolicy.DURABLE,
                        review_required=False,
                        actor_id=actor_id,
                        space_id=space_id,
                        source_observation_id=source_observation_id,
                    )
                )
    return candidates
