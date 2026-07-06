"""Prompt budget observability tests."""

from __future__ import annotations

from iris.contracts.prompting import (
    PromptAssemblyReport,
    PromptOverflowBehavior,
    PromptProfileName,
    PromptSectionAssemblyReport,
    PromptSectionKind,
    PromptTrustBoundary,
)
from iris.runtime.prompting.observability import record_prompt_assembly_report


class RecordingLogger:
    """RuntimeLogger テストダブル。"""

    def __init__(self) -> None:
        """記録用バッファを初期化する。"""
        self.events: list[tuple[str, dict[str, str | float | bool | None]]] = []

    def debug(self, event: str, **fields: str | float | bool | None) -> None:
        self.events.append((event, dict(fields)))

    def info(self, event: str, **fields: str | float | bool | None) -> None:
        self.events.append((event, dict(fields)))

    def warning(self, event: str, **fields: str | float | bool | None) -> None:
        self.events.append((event, dict(fields)))

    def error(self, event: str, **fields: str | float | bool | None) -> None:
        self.events.append((event, dict(fields)))


def test_prompt_budget_observability_excludes_prompt_text() -> None:
    """Prompt observability は本文を出さず size / section metadata だけを記録する。"""
    logger = RecordingLogger()
    report = PromptAssemblyReport(
        profile=PromptProfileName.LOCAL_BALANCED,
        total_chars=10,
        total_max_chars=100,
        persona_profile_version="fallback-v1",
        persona_fallback_used=True,
        persona_failure_reason="persona file not found",
        section_reports=(
            PromptSectionAssemblyReport(
                kind=PromptSectionKind.USER_MEMORY,
                trust_boundary=PromptTrustBoundary.EXTERNAL_CONTEXT,
                input_chars=200,
                output_chars=100,
                input_items=5,
                output_items=3,
                max_chars=100,
                max_items=3,
                priority=50,
                overflow_behavior=PromptOverflowBehavior.TRUNCATE_ITEMS,
                truncated_chars=100,
                truncated_items=2,
            ),
        ),
    )

    record_prompt_assembly_report(report, runtime_logger=logger)

    assert logger.events[0][0] == "runtime.prompt_budget.assembly"
    assert logger.events[0][1]["profile"] == "local_balanced"
    assert logger.events[0][1]["prompt_total_chars"] == 10
    assert logger.events[0][1]["persona_failure_reason"] == "persona file not found"
    assert logger.events[1][0] == "runtime.prompt_budget.section"
    assert logger.events[1][1]["section_kind"] == "user_memory"
    forbidden_keys = {"prompt", "prompt_text", "text", "user_text", "system_instruction"}
    assert all(forbidden_keys.isdisjoint(fields) for _, fields in logger.events)
