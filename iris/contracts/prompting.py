"""Prompt section budget と assembly report の共有契約。"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class PromptProfileName(StrEnum):
    """Prompt budget profile 名。"""

    LOCAL_LOW = "local_low"
    LOCAL_BALANCED = "local_balanced"
    LOCAL_QUALITY = "local_quality"
    PROACTIVE_SHORT = "proactive_short"


class PromptSectionKind(StrEnum):
    """Prompt assembly が扱う section 種別。"""

    SYSTEM = "system"
    PERSONA = "persona"
    SAFETY_CONSTRAINTS = "safety_constraints"
    RECENT_CONVERSATION = "recent_conversation"
    USER_MEMORY = "user_memory"
    PROJECT_MEMORY = "project_memory"
    RELATIONSHIP_SIGNAL = "relationship_signal"
    INTERNAL_STATE = "internal_state"
    INTERACTION_POLICY = "interaction_policy"
    TASK_CONTEXT = "task_context"
    USER_INPUT = "user_input"


class PromptTrustBoundary(StrEnum):
    """Prompt section の信頼境界。"""

    TRUSTED = "trusted"
    INTERNAL_DERIVED = "internal_derived"
    EXTERNAL_CONTEXT = "external_context"
    USER_INPUT = "user_input"


class PromptOverflowBehavior(StrEnum):
    """Budget overflow 時の deterministic policy。"""

    REQUIRED = "required"
    TRUNCATE = "truncate"
    TRUNCATE_ITEMS = "truncate_items"
    OMIT = "omit"
    USE_EXISTING_SUMMARY_THEN_TRUNCATE = "use_existing_summary_then_truncate"


class PromptSectionBudget(BaseModel):
    """単一 prompt section の budget。"""

    model_config = ConfigDict(frozen=True)

    max_chars: int = Field(ge=0)
    max_items: int = Field(ge=0)
    priority: int = Field(ge=0)
    overflow_behavior: PromptOverflowBehavior


class PromptProfileSectionBudget(BaseModel):
    """Profile 内の section kind と budget の対応。"""

    model_config = ConfigDict(frozen=True)

    kind: PromptSectionKind
    budget: PromptSectionBudget


class PromptProfileBudget(BaseModel):
    """Profile 全体の prompt budget。"""

    model_config = ConfigDict(frozen=True)

    name: PromptProfileName
    total_max_chars: int = Field(ge=0)
    sections: tuple[PromptProfileSectionBudget, ...]

    def section_budget(self, kind: PromptSectionKind) -> PromptSectionBudget:
        """Section kind に対応する budget を返す。

        Args:
            kind: 参照対象の prompt section kind。

        Returns:
            対応する prompt section budget。

        Raises:
            KeyError: 指定 section kind が profile に含まれない場合。
        """
        for section in self.sections:
            if section.kind is kind:
                return section.budget
        raise KeyError(kind.value)


class PromptSectionInput(BaseModel):
    """Budget 適用前の prompt section。"""

    model_config = ConfigDict(frozen=True)

    kind: PromptSectionKind
    title: str
    trust_boundary: PromptTrustBoundary
    content: str = ""
    items: tuple[str, ...] = ()


class PromptSectionAssemblyReport(BaseModel):
    """単一 section の budget 適用結果メタデータ。"""

    model_config = ConfigDict(frozen=True)

    kind: PromptSectionKind
    trust_boundary: PromptTrustBoundary
    input_chars: int = Field(ge=0)
    output_chars: int = Field(ge=0)
    input_items: int = Field(ge=0)
    output_items: int = Field(ge=0)
    max_chars: int = Field(ge=0)
    max_items: int = Field(ge=0)
    priority: int = Field(ge=0)
    overflow_behavior: PromptOverflowBehavior
    omitted: bool = False
    truncated_chars: int = Field(default=0, ge=0)
    truncated_items: int = Field(default=0, ge=0)


class PromptAssemblyReport(BaseModel):
    """Prompt assembly 全体の observability 用 report。"""

    model_config = ConfigDict(frozen=True)

    profile: PromptProfileName
    total_chars: int = Field(ge=0)
    total_max_chars: int = Field(ge=0)
    section_reports: tuple[PromptSectionAssemblyReport, ...]
    persona_profile_version: str | None = None
    persona_fallback_used: bool = False

    @property
    def omitted_section_count(self) -> int:
        """省略された section 数。"""
        return sum(1 for report in self.section_reports if report.omitted)

    @property
    def truncated_section_count(self) -> int:
        """文字または item が切り詰められた section 数。"""
        return sum(
            1
            for report in self.section_reports
            if report.truncated_chars > 0 or report.truncated_items > 0
        )

    @property
    def truncated_item_count(self) -> int:
        """切り捨てられた item 数。"""
        return sum(report.truncated_items for report in self.section_reports)
