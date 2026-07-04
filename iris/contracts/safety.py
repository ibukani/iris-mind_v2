"""安全文脈検出とポリシー伝搬の型付き契約。"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SafetyContextCategory(StrEnum):
    """高リスクまたはセンシティブ文脈の分類。"""

    SELF_HARM = "self_harm"
    ABUSE = "abuse"
    VIOLENCE = "violence"
    ILLEGAL_OR_DANGEROUS = "illegal_or_dangerous"
    PERSONAL_DATA = "personal_data"
    UNKNOWN_HIGH_RISK = "unknown_high_risk"


class SafetyContextSeverity(StrEnum):
    """安全文脈の深刻度。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SafetyContextSource(StrEnum):
    """安全文脈を検出した入力面または生成面。"""

    USER_INITIATED = "user_initiated"
    PROACTIVE = "proactive"
    GENERATED_OUTPUT = "generated_output"


class SafetyResponseDirective(StrEnum):
    """検出文脈に対する応答方針。"""

    ALLOW_SUPPORT = "allow_support"
    SAFE_REDIRECT = "safe_redirect"
    REFUSE = "refuse"
    BLOCK = "block"


class SafetyContextReason(BaseModel):
    """Raw content を含めない安全文脈の理由 metadata。"""

    model_config = ConfigDict(frozen=True)

    code: str
    description: str

    @field_validator("code", "description")
    @classmethod
    def _must_not_be_blank(cls, value: str) -> str:
        """空文字 metadata を拒否する。

        Returns:
            前後空白を取り除いた metadata 値。

        Raises:
            ValueError: 空白のみの場合。
        """
        normalized = value.strip()
        if not normalized:
            message = "safety context reason metadata must not be blank"
            raise ValueError(message)
        return normalized


class SafetyContext(BaseModel):
    """policy / delivery / observability へ渡す高リスク文脈 metadata。"""

    model_config = ConfigDict(frozen=True)

    category: SafetyContextCategory
    severity: SafetyContextSeverity
    source: SafetyContextSource
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: tuple[SafetyContextReason, ...]
    directive: SafetyResponseDirective

    @field_validator("reasons")
    @classmethod
    def _must_include_reason(
        cls,
        value: tuple[SafetyContextReason, ...],
    ) -> tuple[SafetyContextReason, ...]:
        """少なくとも1件の理由 metadata を要求する。

        Returns:
            検証済み reasons。

        Raises:
            ValueError: reason が空の場合。
        """
        if not value:
            message = "safety context must include at least one reason"
            raise ValueError(message)
        return value
