"""Prompting contract tests."""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from iris.contracts.prompting import (
    PromptAssemblyReport,
    PromptOverflowBehavior,
    PromptProfileName,
    PromptSectionAssemblyReport,
    PromptSectionBudget,
    PromptSectionKind,
    PromptTrustBoundary,
)


def test_prompt_section_budget_rejects_negative_values() -> None:
    """Section budget は負の char / item / priority を拒否する。"""
    with pytest.raises(ValidationError):
        PromptSectionBudget(
            max_chars=-1,
            max_items=1,
            priority=1,
            overflow_behavior=PromptOverflowBehavior.TRUNCATE,
        )


def test_prompt_assembly_report_counts_overflow_results() -> None:
    """Assembly report は omitted / truncated count を安全メタデータだけで計算する。"""
    report = PromptAssemblyReport(
        profile=PromptProfileName.LOCAL_LOW,
        total_chars=10,
        total_max_chars=100,
        section_reports=(
            PromptSectionAssemblyReport(
                kind=PromptSectionKind.USER_MEMORY,
                trust_boundary=PromptTrustBoundary.EXTERNAL_CONTEXT,
                input_chars=20,
                output_chars=10,
                input_items=3,
                output_items=2,
                max_chars=10,
                max_items=2,
                priority=50,
                overflow_behavior=PromptOverflowBehavior.TRUNCATE_ITEMS,
                truncated_chars=10,
                truncated_items=1,
            ),
            PromptSectionAssemblyReport(
                kind=PromptSectionKind.PROJECT_MEMORY,
                trust_boundary=PromptTrustBoundary.EXTERNAL_CONTEXT,
                input_chars=12,
                output_chars=0,
                input_items=1,
                output_items=0,
                max_chars=0,
                max_items=0,
                priority=10,
                overflow_behavior=PromptOverflowBehavior.OMIT,
                omitted=True,
                truncated_chars=12,
                truncated_items=1,
            ),
        ),
    )

    assert report.omitted_section_count == 1
    assert report.truncated_section_count == 2
    assert report.truncated_item_count == 2
