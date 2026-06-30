"""Memory write policy: accept/reject candidates before storage."""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.cognitive.memory.candidates import (
    MemoryCandidateSensitivity,
    MemoryCandidateSource,
    MemoryRetentionPolicy,
)
from iris.cognitive.memory.safety import (
    contains_credential_like_content,
    contains_sensitive_profile_content,
    is_unsafe_preferred_name_memory_text,
)

if TYPE_CHECKING:
    from iris.cognitive.memory.candidates import MemoryCandidate

_EXPLICIT_SOURCES = frozenset(
    {
        MemoryCandidateSource.EXPLICIT_USER_REQUEST,
        MemoryCandidateSource.EXPLICIT_PROFILE_STATEMENT,
        MemoryCandidateSource.EXPLICIT_PREFERENCE_STATEMENT,
        MemoryCandidateSource.EXPLICIT_USER_INSTRUCTION,
        MemoryCandidateSource.EXPLICIT_PREFERENCE,
    }
)

_ACCEPTED_RETENTION_POLICIES = frozenset(
    {
        MemoryRetentionPolicy.DURABLE,
        MemoryRetentionPolicy.LONG_TERM,
        MemoryRetentionPolicy.UNTIL_CHANGED,
    }
)

_ACCEPTED_SENSITIVITY = frozenset(
    {
        MemoryCandidateSensitivity.NORMAL,
        MemoryCandidateSensitivity.PERSONAL,
    }
)


class MemoryWritePolicy:
    """保存候補を受け入れまたは拒否するポリシー。"""

    def __init__(
        self,
        *,
        min_salience: float = 0.0,
        min_confidence: float = 0.6,
        max_text_length: int = 5000,
    ) -> None:
        """しきい値と制約で初期化する。

        Args:
            min_salience: 受け入れる最小 salience。
            min_confidence: 受け入れる最小 confidence。
            max_text_length: 受け入れる最大テキスト長（文字数）。
        """
        self._min_salience = min_salience
        self._min_confidence = min_confidence
        self._max_text_length = max_text_length

    def accept(self, candidate: MemoryCandidate) -> bool:
        """候補が保存可能か判定する。

        Args:
            candidate: 判定対象の保存候補。

        Returns:
            bool: 保存を許可する場合は True。
        """
        text = candidate.text.strip()
        if self._has_invalid_content(text, candidate):
            return False
        if self._has_invalid_provenance(candidate):
            return False
        return not self._has_safety_rejected_content(text)

    def _has_invalid_content(self, text: str, candidate: MemoryCandidate) -> bool:
        """内容・しきい値の観点で保存不可か判定する。

        Returns:
            bool: 保存不可の場合は True。
        """
        return (
            not text
            or len(text) > self._max_text_length
            or candidate.salience < self._min_salience
            or candidate.confidence < self._min_confidence
        )

    @staticmethod
    def _has_invalid_provenance(candidate: MemoryCandidate) -> bool:
        """生成経路・保存方針・機微度の観点で保存不可か判定する。

        Returns:
            bool: 保存不可の場合は True。
        """
        return (
            candidate.source not in _EXPLICIT_SOURCES
            or candidate.retention_policy not in _ACCEPTED_RETENTION_POLICIES
            or candidate.sensitivity not in _ACCEPTED_SENSITIVITY
            or candidate.review_required
        )

    @staticmethod
    def _has_safety_rejected_content(text: str) -> bool:
        """正規化済み候補テキストから誤保存リスクを検出する。

        Returns:
            bool: hot path 保存を避けるべき場合は True。
        """
        return (
            contains_credential_like_content(text)
            or contains_sensitive_profile_content(text)
            or is_unsafe_preferred_name_memory_text(text)
        )
