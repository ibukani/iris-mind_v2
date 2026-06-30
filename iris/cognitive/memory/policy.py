"""Memory write policy: accept/reject candidates before storage."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from iris.cognitive.memory.candidates import (
    MemoryCandidateSensitivity,
    MemoryCandidateSource,
    MemoryRetentionPolicy,
)

if TYPE_CHECKING:
    from iris.cognitive.memory.candidates import MemoryCandidate

_SECRET_PATTERNS = (
    r"api\s*key",
    r"apikey",
    r"secret",
    r"token",
    r"password",
    r"passwd",
    r"bearer",
    r"OPENAI_API_KEY",
    r"sk-",
    r"github_pat_",
    r"パスワード",
    r"トークン",
    r"秘密鍵",
    r"認証情報",
    r"API\s*キー",
    r"api\s*キー",
)

_SENSITIVE_PROFILE_PATTERNS = (
    r"うつ病",
    r"鬱病",
    r"統合失調症",
    r"双極性障害",
    r"発達障害",
    r"ADHD",
    r"自閉",
    r"癌",
    r"がん患者",
    r"キリスト教徒",
    r"イスラム教徒",
    r"ユダヤ教徒",
    r"仏教徒",
    r"右翼",
    r"左翼",
    r"保守派",
    r"リベラル",
    r"自民党支持",
    r"共産党支持",
    r"ゲイ",
    r"レズビアン",
    r"バイセクシュアル",
    r"トランスジェンダー",
    r"LGBT",
    r"depression",
    r"depressed",
    r"schizophrenia",
    r"bipolar",
    r"autistic",
    r"cancer",
    r"Christian",
    r"Muslim",
    r"Jewish",
    r"Buddhist",
    r"conservative",
    r"liberal",
    r"Democrat",
    r"Republican",
    r"gay",
    r"lesbian",
    r"bisexual",
    r"transgender",
)

_UNSAFE_PREFERRED_NAME_PATTERNS = (
    r"^ユーザーの希望呼称は「.*[をに].*」。$",
    r"^ユーザーの希望呼称は「(?:この|その|あの|これ|それ|あれ|彼|彼女|変数|プロジェクト|関数|クラス).*」。$",
    r"^User's preferred name is (?:this|that|him|her|them|variable|project|function|class)\b",
)

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
        if self._has_safety_rejected_content(text):
            return False
        return not any(re.search(pattern, text, re.IGNORECASE) for pattern in _SECRET_PATTERNS)

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
        patterns = (*_SENSITIVE_PROFILE_PATTERNS, *_UNSAFE_PREFERRED_NAME_PATTERNS)
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)
