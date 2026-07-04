"""Basic output safety gate with minimal production-relevant checks."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, override
import unicodedata

from iris.safety.action_gate import GateDecision, SafetyDecision
from iris.safety.output_filter import OutputSafetyGate

if TYPE_CHECKING:
    from iris.contracts.actions import PresentedOutput


_SECRET_PATTERNS = (
    r"OPENAI_API_KEY",
    r"ANTHROPIC_API_KEY",
    r"GOOGLE_API_KEY",
    r"sk-[a-zA-Z0-9\-]{10,}",
    r"ghp_[a-zA-Z0-9]{10,}",
    r"github_pat_[a-zA-Z0-9]{10,}",
)


def _contains_secret(text: str) -> bool:
    lowered = text.casefold()
    return any(re.search(pattern, lowered) for pattern in _SECRET_PATTERNS)


def _contains_control_characters(text: str) -> bool:
    for ch in text:
        cat = unicodedata.category(ch)
        if cat in {"Cc", "Cf"} and ch not in {"\n", "\r", "\t"}:
            return True
    return False


def _contains_high_risk_instruction(text: str) -> bool:
    normalized = text.casefold()
    harmful_terms = (
        "kill yourself",
        "commit suicide",
        "overdose",
        "build a bomb",
        "make a bomb",
        "poison someone",
        "steal password",
        "exfiltrate credentials",
        "自殺し",
        "爆弾を作",
    )
    return any(term in normalized for term in harmful_terms)


_MAX_OUTPUT_CHARS = 4000


class BasicOutputSafetyGate(OutputSafetyGate):
    """最小限のプロダクション関連チェックを備えた出力安全性ゲート。

    チェック:
    - 最大出力長超過
    - 明らかなシークレットパターン
    - 制御文字

    これらのチェックは包括的なコンテンツモデレーションを意図していない。
    """

    def __init__(self, *, max_output_chars: int = _MAX_OUTPUT_CHARS) -> None:
        """上限値で初期化する。

        Args:
            max_output_chars: 許容する最大出力文字数。
        """
        self._max_output_chars = max_output_chars

    @override
    async def check_output(self, output: PresentedOutput) -> SafetyDecision:
        """PresentedOutput を評価し、安全性判定を返す。

        Args:
            output: 検査対象の PresentedOutput。

        Returns:
            decision=BLOCK or ALLOW の SafetyDecision。
        """
        if output.text is None:
            return SafetyDecision(decision=GateDecision.ALLOW)

        text = output.text
        reason: str | None = None

        if len(text) > self._max_output_chars:
            reason = f"output exceeds max length ({len(text)} > {self._max_output_chars})"
        elif _contains_secret(text):
            reason = "output contains a secret-like pattern"
        elif _contains_control_characters(text):
            reason = "output contains control characters"
        elif _contains_high_risk_instruction(text):
            reason = "output contains high-risk actionable guidance"

        return SafetyDecision(
            decision=GateDecision.BLOCK if reason else GateDecision.ALLOW,
            reason=reason,
        )
