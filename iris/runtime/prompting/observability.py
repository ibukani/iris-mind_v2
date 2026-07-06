"""Prompt budget observability helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.runtime.observability.context import trace_counter_extra
from iris.runtime.observability.logger import LoguruRuntimeLogger

if TYPE_CHECKING:
    from iris.contracts.prompting import PromptAssemblyReport
    from iris.runtime.observability.ports import RuntimeLogger


def record_prompt_assembly_report(
    report: PromptAssemblyReport,
    *,
    runtime_logger: RuntimeLogger | None = None,
) -> None:
    """Prompt 本文を含めず、section size と overflow 結果だけを記録する。"""
    logger = runtime_logger or LoguruRuntimeLogger()
    summary_fields = trace_counter_extra()
    summary_fields.update(
        {
            "profile": report.profile.value,
            "prompt_total_chars": report.total_chars,
            "prompt_total_max_chars": report.total_max_chars,
            "section_count": len(report.section_reports),
            "omitted_section_count": report.omitted_section_count,
            "truncated_section_count": report.truncated_section_count,
            "truncated_item_count": report.truncated_item_count,
            "persona_profile_version": report.persona_profile_version,
            "persona_fallback_used": report.persona_fallback_used,
        }
    )
    logger.info("runtime.prompt_budget.assembly", **summary_fields)
    for section_report in report.section_reports:
        section_fields = trace_counter_extra()
        section_fields.update(
            {
                "profile": report.profile.value,
                "section_kind": section_report.kind.value,
                "trust_boundary": section_report.trust_boundary.value,
                "input_chars": section_report.input_chars,
                "output_chars": section_report.output_chars,
                "input_items": section_report.input_items,
                "output_items": section_report.output_items,
                "max_chars": section_report.max_chars,
                "max_items": section_report.max_items,
                "priority": section_report.priority,
                "overflow_behavior": section_report.overflow_behavior.value,
                "omitted": section_report.omitted,
                "truncated_chars": section_report.truncated_chars,
                "truncated_items": section_report.truncated_items,
            }
        )
        logger.debug("runtime.prompt_budget.section", **section_fields)
