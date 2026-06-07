"""Memory write policy: accept/reject candidates before storage."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

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


class MemoryWritePolicy:
    """保存候補を受け入れまたは拒否するポリシー。"""

    def __init__(
        self,
        *,
        min_salience: float = 0.0,
        min_confidence: float = 0.0,
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
        if not text or len(text) > self._max_text_length:
            return False
        if candidate.salience < self._min_salience:
            return False
        if candidate.confidence < self._min_confidence:
            return False
        lowered = text.casefold()
        return not any(re.search(pattern, lowered, re.IGNORECASE) for pattern in _SECRET_PATTERNS)
