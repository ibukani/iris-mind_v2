"""Rule-based memory candidate extraction from interpreted input text."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, override

from iris.cognitive.memory.candidates import (
    MemoryCandidate,
    MemoryCandidateExtractor,
    MemoryCandidateSensitivity,
    MemoryCandidateSource,
    MemoryRetentionPolicy,
)
from iris.cognitive.memory.safety import (
    contains_sensitive_profile_content,
    is_safe_preferred_name,
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
_NAME_PATTERNS = (
    r"^(?:私|わたし|僕|俺|自分)の名前は(.+?)(?:です|だ)?[。.!]?$",
    r"^(?:my name is)\s+(.+?)[\.!]?$",
)
_SELF_IDENTIFICATION_PATTERNS = (
    r"^(?:私は|わたしは|僕は|俺は)(?!.*(?:が好き|を好む|が嫌い|を嫌う))(.+?)(?:です|だ)[。.!]?$",
    r"^(?:I am|I'm)\s+(.+?)[\.!]?$",
)
_PREFERRED_NAME_PATTERNS = (
    r"^(?:私|わたし|僕|俺|自分)(?:を)?(.+?)(?:と|って)呼んで(?:ください|ほしい)?[。.!]?$",
    r"^(.+?)(?:と|って)呼んで(?:ください|ほしい)?[。.!]?$",
    r"^call me\s+(.+?)[\.!]?$",
    r"^please call me\s+(.+?)[\.!]?$",
)
_JA_STABLE_PREFERENCE_PATTERNS = (
    (
        r"^(?:私は|わたしは|僕は|俺は|自分は)(.+?)(?:が|を)好き(?:です|だ)?[。.!]?$",
        "好き",
    ),
    (r"^(?:私は|わたしは|僕は|俺は|自分は)(.+?)(?:が|を)好む[。.!]?$", "好む"),
    (
        r"^(?:私は|わたしは|僕は|俺は|自分は)(.+?)(?:が|を)嫌い(?:です|だ)?[。.!]?$",
        "嫌い",
    ),
)
_EN_STABLE_PREFERENCE_PATTERNS = (
    (r"^I (?:like|love)\s+(.+?)[\.!]?$", "like"),
    (r"^I prefer\s+(.+?)[\.!]?$", "prefer"),
    (r"^I (?:dislike|hate)\s+(.+?)[\.!]?$", "dislike"),
)
_RESPONSE_STYLE_JA_PATTERNS = (
    r"(?:今後|これから|以後|次から).*(?:短め|短く|簡潔|端的).*(?:答えて|回答して|返して)",
    r"(?:短め|短く|簡潔|端的).*(?:答えて|回答して|返して).*(?:今後|これから|以後|次から)",
)
_RESPONSE_STYLE_EN_PATTERNS = (
    r"(?:please\s+)?(?:answer|respond|reply)\s+(?:briefly|concisely)\s+from now on",
    r"keep (?:your )?(?:answers|responses|replies) (?:short|brief|concise)",
)
_LANGUAGE_SUBJECT_PATTERNS = (
    r"^(.+?)は日本語で(?:書いて|書く|答えて|回答して)ほしい[。.!]?$",
    r"^write\s+(.+?)\s+in Japanese[\.!]?$",
)
_LANGUAGE_PREFERENCE_PATTERNS = (
    r"(?:今後|これから|以後|次から)?.*日本語で(?:答えて|回答して|返して)ほしい?",
    r"(?:今後|これから|以後|次から)?.*日本語で(?:答えて|回答して|返して)",
    r"(?:please\s+)?(?:answer|respond|reply)\s+in Japanese",
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

        text = frame.interpreted_input.text.strip()
        actor = frame.actor_context.actor
        actor_id: ActorId | None = actor.actor_id if actor is not None else None
        space_id: SpaceId | None = frame.space_context.space_id
        source_observation_id: ObservationId = frame.observation.observation_id

        if any(re.search(pattern, text, re.IGNORECASE) for pattern in _SKIP_PATTERNS):
            return ()

        candidates: list[MemoryCandidate] = []
        candidates.extend(_extract_remember(text, actor_id, space_id, source_observation_id))
        candidates.extend(
            _extract_profile_statements(text, actor_id, space_id, source_observation_id)
        )
        candidates.extend(
            _extract_preferred_names(text, actor_id, space_id, source_observation_id)
        )
        candidates.extend(
            _extract_stable_preferences(text, actor_id, space_id, source_observation_id)
        )
        candidates.extend(
            _extract_response_style(text, actor_id, space_id, source_observation_id)
        )
        candidates.extend(
            _extract_language_preferences(text, actor_id, space_id, source_observation_id)
        )
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
        if match is None:
            continue
        content = _clean_memory_value(match.group(1))
        if not content:
            continue
        candidates.append(
            MemoryCandidate(
                text=content,
                kind=MemoryKind.NOTE,
                salience=0.8,
                confidence=0.9,
                source=MemoryCandidateSource.EXPLICIT_USER_REQUEST,
                reason="user explicitly requested durable memory",
                retention_policy=MemoryRetentionPolicy.DURABLE,
                sensitivity=MemoryCandidateSensitivity.NORMAL,
                review_required=False,
                actor_id=actor_id,
                space_id=space_id,
                source_observation_id=source_observation_id,
            )
        )
    return candidates


def _extract_profile_statements(
    text: str,
    actor_id: ActorId | None,
    space_id: SpaceId | None,
    source_observation_id: ObservationId,
) -> list[MemoryCandidate]:
    """明示的な名前・自己紹介文から profile 候補を抽出する。

    Returns:
        list[MemoryCandidate]: 抽出された候補リスト。
    """
    name = _first_capture(text, _NAME_PATTERNS)
    if name:
        return [
            MemoryCandidate(
                text=f"ユーザーの名前は「{name}」。",
                kind=MemoryKind.FACT,
                salience=0.9,
                confidence=0.95,
                source=MemoryCandidateSource.EXPLICIT_PROFILE_STATEMENT,
                reason="user stated their name",
                retention_policy=MemoryRetentionPolicy.UNTIL_CHANGED,
                sensitivity=MemoryCandidateSensitivity.PERSONAL,
                review_required=False,
                actor_id=actor_id,
                space_id=space_id,
                source_observation_id=source_observation_id,
            )
        ]
    self_identification = _first_capture(text, _SELF_IDENTIFICATION_PATTERNS)
    if not self_identification:
        return []
    is_sensitive = contains_sensitive_profile_content(self_identification)
    return [
        MemoryCandidate(
            text=f"ユーザーは「{self_identification}」と自己紹介した。",
            kind=MemoryKind.FACT,
            salience=0.75,
            confidence=0.8,
            source=MemoryCandidateSource.EXPLICIT_PROFILE_STATEMENT,
            reason=(
                "user stated potentially sensitive profile information"
                if is_sensitive
                else "user explicitly self-identified"
            ),
            retention_policy=(
                MemoryRetentionPolicy.REVIEW_REQUIRED
                if is_sensitive
                else MemoryRetentionPolicy.UNTIL_CHANGED
            ),
            sensitivity=(
                MemoryCandidateSensitivity.SENSITIVE
                if is_sensitive
                else MemoryCandidateSensitivity.PERSONAL
            ),
            review_required=is_sensitive,
            actor_id=actor_id,
            space_id=space_id,
            source_observation_id=source_observation_id,
        )
    ]


def _extract_preferred_names(
    text: str,
    actor_id: ActorId | None,
    space_id: SpaceId | None,
    source_observation_id: ObservationId,
) -> list[MemoryCandidate]:
    """希望呼称・ニックネームの明示指示から候補を抽出する。

    Returns:
        list[MemoryCandidate]: 抽出された候補リスト。
    """
    preferred_name = _first_capture(text, _PREFERRED_NAME_PATTERNS)
    if not preferred_name or not is_safe_preferred_name(preferred_name):
        return []
    return [
        MemoryCandidate(
            text=f"ユーザーの希望呼称は「{preferred_name}」。",
            kind=MemoryKind.PREFERENCE,
            salience=0.9,
            confidence=0.95,
            source=MemoryCandidateSource.EXPLICIT_PROFILE_STATEMENT,
            reason="user stated their preferred name",
            retention_policy=MemoryRetentionPolicy.UNTIL_CHANGED,
            sensitivity=MemoryCandidateSensitivity.PERSONAL,
            review_required=False,
            actor_id=actor_id,
            space_id=space_id,
            source_observation_id=source_observation_id,
        )
    ]


def _extract_stable_preferences(
    text: str,
    actor_id: ActorId | None,
    space_id: SpaceId | None,
    source_observation_id: ObservationId,
) -> list[MemoryCandidate]:
    """安定した好み・嗜好の明示文から候補を抽出する。

    Returns:
        list[MemoryCandidate]: 抽出された候補リスト。
    """
    preference = _ja_preference_text(text) or _en_preference_text(text)
    if not preference:
        return []
    return [
        MemoryCandidate(
            text=preference,
            kind=MemoryKind.PREFERENCE,
            salience=0.75,
            confidence=0.88,
            source=MemoryCandidateSource.EXPLICIT_PREFERENCE_STATEMENT,
            reason="user stated a stable preference",
            retention_policy=MemoryRetentionPolicy.LONG_TERM,
            sensitivity=MemoryCandidateSensitivity.NORMAL,
            review_required=False,
            actor_id=actor_id,
            space_id=space_id,
            source_observation_id=source_observation_id,
        )
    ]


def _extract_response_style(
    text: str,
    actor_id: ActorId | None,
    space_id: SpaceId | None,
    source_observation_id: ObservationId,
) -> list[MemoryCandidate]:
    """応答スタイルに関する明示的な長期指示から候補を抽出する。

    Returns:
        list[MemoryCandidate]: 抽出された候補リスト。
    """
    patterns = (*_RESPONSE_STYLE_JA_PATTERNS, *_RESPONSE_STYLE_EN_PATTERNS)
    if not any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns):
        return []
    return [
        MemoryCandidate(
            text="ユーザーは回答を短め・簡潔にすることを希望している。",
            kind=MemoryKind.PREFERENCE,
            salience=0.8,
            confidence=0.9,
            source=MemoryCandidateSource.EXPLICIT_USER_INSTRUCTION,
            reason="user stated a response style preference",
            retention_policy=MemoryRetentionPolicy.UNTIL_CHANGED,
            sensitivity=MemoryCandidateSensitivity.NORMAL,
            review_required=False,
            actor_id=actor_id,
            space_id=space_id,
            source_observation_id=source_observation_id,
        )
    ]


def _extract_language_preferences(
    text: str,
    actor_id: ActorId | None,
    space_id: SpaceId | None,
    source_observation_id: ObservationId,
) -> list[MemoryCandidate]:
    """言語設定・日本語利用の明示指示から候補を抽出する。

    Returns:
        list[MemoryCandidate]: 抽出された候補リスト。
    """
    subject = _first_capture(text, _LANGUAGE_SUBJECT_PATTERNS)
    if subject:
        candidate_text = f"「{subject}」は日本語で書く。"
    elif any(re.search(pattern, text, re.IGNORECASE) for pattern in _LANGUAGE_PREFERENCE_PATTERNS):
        candidate_text = "ユーザーは日本語での応答を希望している。"
    else:
        return []
    return [
        MemoryCandidate(
            text=candidate_text,
            kind=MemoryKind.PREFERENCE,
            salience=0.8,
            confidence=0.9,
            source=MemoryCandidateSource.EXPLICIT_USER_INSTRUCTION,
            reason="user stated a language preference",
            retention_policy=MemoryRetentionPolicy.UNTIL_CHANGED,
            sensitivity=MemoryCandidateSensitivity.NORMAL,
            review_required=False,
            actor_id=actor_id,
            space_id=space_id,
            source_observation_id=source_observation_id,
        )
    ]


def _ja_preference_text(text: str) -> str | None:
    """日本語の安定嗜好文を正規化する。

    Returns:
        str | None: 正規化された preference 文。
    """
    for pattern, disposition in _JA_STABLE_PREFERENCE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match is None:
            continue
        target = _clean_memory_value(match.group(1))
        if target:
            return f"ユーザーは「{target}」が{disposition}。"
    return None


def _en_preference_text(text: str) -> str | None:
    """英語の安定嗜好文を正規化する。

    Returns:
        str | None: 正規化された preference 文。
    """
    for pattern, disposition in _EN_STABLE_PREFERENCE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match is None:
            continue
        target = _clean_memory_value(match.group(1))
        if target:
            return f"User {disposition}s {target}."
    return None


def _first_capture(text: str, patterns: tuple[str, ...]) -> str | None:
    """最初に一致した正規表現の第 1 キャプチャを返す。

    Returns:
        str | None: 正規化されたキャプチャ文字列。
    """
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match is None:
            continue
        value = _clean_memory_value(match.group(1))
        if value:
            return value
    return None


def _clean_memory_value(value: str) -> str:
    """抽出値の周辺記号を取り除く。

    Returns:
        str: 正規化された文字列。
    """
    return value.strip().strip(" \t\n\r。.!?'\"「」『』")
