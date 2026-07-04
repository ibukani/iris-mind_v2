"""Prompt budget policy tests."""

from __future__ import annotations

from iris.contracts.prompting import (
    PromptOverflowBehavior,
    PromptProfileName,
    PromptSectionInput,
    PromptSectionKind,
    PromptTrustBoundary,
)
from iris.runtime.config.prompt_budget import RuntimePromptBudgetConfig, RuntimePromptSectionBudget
from iris.runtime.prompting.budget import PromptBudgetPolicy


def test_prompt_budget_truncates_items_deterministically() -> None:
    """Item budget は deterministic に先頭から保持する。"""
    config = RuntimePromptBudgetConfig()
    result = PromptBudgetPolicy(
        PromptProfileName.LOCAL_BALANCED,
        config.local_balanced,
    ).apply(
        (
            PromptSectionInput(
                kind=PromptSectionKind.USER_MEMORY,
                title="Relevant memories",
                trust_boundary=PromptTrustBoundary.EXTERNAL_CONTEXT,
                items=("m1", "m2", "m3", "m4", "m5", "m6"),
            ),
        )
    )

    assert len(result.sections) == 1
    assert "m1" in result.sections[0].content
    assert "m5" in result.sections[0].content
    assert "m6" not in result.sections[0].content
    assert result.report.section_reports[0].truncated_items == 1


def test_prompt_budget_recent_conversation_keeps_latest_items() -> None:
    """recent_conversation は古い item から落とす。"""
    config = RuntimePromptBudgetConfig()
    result = PromptBudgetPolicy(
        PromptProfileName.PROACTIVE_SHORT,
        config.proactive_short,
    ).apply(
        (
            PromptSectionInput(
                kind=PromptSectionKind.RECENT_CONVERSATION,
                title="Recent conversation",
                trust_boundary=PromptTrustBoundary.INTERNAL_DERIVED,
                items=("old", "middle", "near", "latest"),
            ),
        )
    )

    assert "old" not in result.sections[0].content
    assert "middle" in result.sections[0].content
    assert "near" in result.sections[0].content
    assert "latest" in result.sections[0].content


def test_prompt_budget_omits_zero_budget_external_section() -> None:
    """max_chars=0 の external section は deterministic に omit される。"""
    config = RuntimePromptBudgetConfig()
    result = PromptBudgetPolicy(
        PromptProfileName.PROACTIVE_SHORT,
        config.proactive_short,
    ).apply(
        (
            PromptSectionInput(
                kind=PromptSectionKind.PROJECT_MEMORY,
                title="Project memory",
                trust_boundary=PromptTrustBoundary.EXTERNAL_CONTEXT,
                items=("project item",),
            ),
        )
    )

    assert result.sections == ()
    assert result.report.omitted_section_count == 1
    assert result.report.section_reports[0].omitted


def test_prompt_budget_total_overflow_drops_lower_priority_first() -> None:
    """Total budget 超過時は priority の低い section から削る。"""
    config = RuntimePromptBudgetConfig()
    low_budget = config.local_low
    low_budget = low_budget.__class__(
        total_max_chars=60,
        system=RuntimePromptSectionBudget(
            max_chars=50,
            max_items=1,
            priority=100,
            overflow_behavior=PromptOverflowBehavior.REQUIRED,
        ),
        persona=low_budget.persona,
        safety_constraints=low_budget.safety_constraints,
        recent_conversation=low_budget.recent_conversation,
        user_memory=low_budget.user_memory,
        project_memory=low_budget.project_memory,
        relationship_signal=low_budget.relationship_signal,
        internal_state=low_budget.internal_state,
        interaction_policy=low_budget.interaction_policy,
        task_context=low_budget.task_context,
        user_input=low_budget.user_input,
    )

    result = PromptBudgetPolicy(PromptProfileName.LOCAL_LOW, low_budget).apply(
        (
            PromptSectionInput(
                kind=PromptSectionKind.SYSTEM,
                title="System",
                trust_boundary=PromptTrustBoundary.TRUSTED,
                content="s" * 40,
            ),
            PromptSectionInput(
                kind=PromptSectionKind.PROJECT_MEMORY,
                title="Project",
                trust_boundary=PromptTrustBoundary.EXTERNAL_CONTEXT,
                content="p" * 40,
            ),
        )
    )

    assert result.report.total_chars <= 60
    assert result.report.section_reports[0].omitted is False
    assert result.report.section_reports[1].truncated_chars > 0
