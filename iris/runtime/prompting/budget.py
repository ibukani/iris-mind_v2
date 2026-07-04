"""Prompt section budget policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.prompting import (
    PromptAssemblyReport,
    PromptOverflowBehavior,
    PromptProfileName,
    PromptSectionAssemblyReport,
    PromptSectionInput,
    PromptSectionKind,
    PromptTrustBoundary,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from iris.runtime.config.prompt_budget import (
        RuntimePromptProfileBudget,
        RuntimePromptSectionBudget,
    )


@dataclass(frozen=True)
class BudgetedPromptSection:
    """Budget 適用後の prompt section。"""

    kind: PromptSectionKind
    title: str
    trust_boundary: PromptTrustBoundary
    content: str
    items: tuple[str, ...] = ()


@dataclass(frozen=True)
class PromptBudgetResult:
    """Budget 適用後の sections と report。"""

    sections: tuple[BudgetedPromptSection, ...]
    report: PromptAssemblyReport


class PromptBudgetPolicy:
    """Profile budget に基づき prompt section を決定論的に圧縮する。"""

    def __init__(
        self,
        profile: PromptProfileName,
        budget: RuntimePromptProfileBudget,
    ) -> None:
        """Profile 名と budget で初期化する。"""
        self._profile = profile
        self._budget = budget

    def apply(self, sections: Iterable[PromptSectionInput]) -> PromptBudgetResult:
        """入力 section に section budget と total budget を適用する。

        Args:
            sections: budget 適用対象の prompt sections。

        Returns:
            budget 適用後の sections と安全な観測用 report。
        """
        section_results = tuple(self._apply_section(section) for section in sections)
        section_results = self._apply_total_budget(section_results)
        output_sections = tuple(
            result.section for result in section_results if result.section is not None
        )
        report = PromptAssemblyReport(
            profile=self._profile,
            total_chars=sum(len(section.content) for section in output_sections),
            total_max_chars=self._budget.total_max_chars,
            section_reports=tuple(result.report for result in section_results),
        )
        return PromptBudgetResult(sections=output_sections, report=report)

    def _apply_section(self, section: PromptSectionInput) -> _SectionBudgetApplication:
        budget = self._budget.section_budget(section.kind)
        rendered = _render_section_content(section)
        input_chars = len(rendered)
        input_items = _input_item_count(section)
        if _section_is_omitted_by_zero_budget(section, budget.max_chars, budget.max_items):
            return _omitted_result(section, budget, input_chars, input_items)
        if section.items:
            return _apply_items_section(section, budget, input_chars, input_items)
        budgeted_text = _text_within_char_budget(rendered, budget)
        if budgeted_text is None:
            return _omitted_result(section, budget, input_chars, input_items)
        return _section_result(
            _SectionComputation(
                section=section,
                budget=budget,
                rendered=budgeted_text,
                kept_items=(),
                input_chars=input_chars,
                input_items=input_items,
                output_items=input_items,
            )
        )

    def _apply_total_budget(
        self,
        results: tuple[_SectionBudgetApplication, ...],
    ) -> tuple[_SectionBudgetApplication, ...]:
        active = tuple(result for result in results if result.section is not None)
        total = sum(len(result.section.content) for result in active if result.section is not None)
        if total <= self._budget.total_max_chars:
            return results

        remaining_overflow = total - self._budget.total_max_chars
        ordered: list[tuple[int, _SectionBudgetApplication]] = []
        for index, result in enumerate(results):
            if (
                result.section is not None
                and result.report.overflow_behavior is not PromptOverflowBehavior.REQUIRED
            ):
                ordered.append((index, result))
        ordered.sort(key=_overflow_sort_key)
        patched = list(results)
        for index, result in ordered:
            if remaining_overflow <= 0 or result.section is None:
                break
            section = result.section
            removable = min(len(section.content), remaining_overflow)
            if removable >= len(section.content):
                patched[index] = _omit_existing(result)
            else:
                new_len = len(section.content) - removable
                patched[index] = _truncate_existing(result, new_len)
            remaining_overflow -= removable
        return tuple(patched)


def _apply_items_section(
    section: PromptSectionInput,
    budget: RuntimePromptSectionBudget,
    input_chars: int,
    input_items: int,
) -> _SectionBudgetApplication:
    kept_items = _items_after_item_budget(section, budget.max_items)
    if len(_render_items(section.title, kept_items)) > budget.max_chars:
        if budget.overflow_behavior is PromptOverflowBehavior.OMIT:
            return _omitted_result(section, budget, input_chars, input_items)
        kept_items = _items_within_char_budget(
            section.kind,
            section.title,
            kept_items,
            budget.max_chars,
        )
    if not kept_items:
        return _omitted_result(section, budget, input_chars, input_items)
    rendered = _render_items(section.title, kept_items)
    return _section_result(
        _SectionComputation(
            section=section,
            budget=budget,
            rendered=rendered,
            kept_items=kept_items,
            input_chars=input_chars,
            input_items=input_items,
            output_items=len(kept_items),
        )
    )


def _text_within_char_budget(
    rendered: str,
    budget: RuntimePromptSectionBudget,
) -> str | None:
    if len(rendered) <= budget.max_chars:
        return rendered
    if budget.overflow_behavior is PromptOverflowBehavior.OMIT:
        return None
    return _truncate_text(rendered, budget.max_chars)


@dataclass(frozen=True)
class _SectionComputation:
    section: PromptSectionInput
    budget: RuntimePromptSectionBudget
    rendered: str
    kept_items: tuple[str, ...]
    input_chars: int
    input_items: int
    output_items: int


def _section_result(computation: _SectionComputation) -> _SectionBudgetApplication:
    output_chars = len(computation.rendered)
    report = PromptSectionAssemblyReport(
        kind=computation.section.kind,
        trust_boundary=computation.section.trust_boundary,
        input_chars=computation.input_chars,
        output_chars=output_chars,
        input_items=computation.input_items,
        output_items=computation.output_items,
        max_chars=computation.budget.max_chars,
        max_items=computation.budget.max_items,
        priority=computation.budget.priority,
        overflow_behavior=computation.budget.overflow_behavior,
        omitted=False,
        truncated_chars=max(computation.input_chars - output_chars, 0),
        truncated_items=max(computation.input_items - computation.output_items, 0),
    )
    return _SectionBudgetApplication(
        section=BudgetedPromptSection(
            kind=computation.section.kind,
            title=computation.section.title,
            trust_boundary=computation.section.trust_boundary,
            content=computation.rendered,
            items=computation.kept_items,
        ),
        report=report,
    )


@dataclass(frozen=True)
class _SectionBudgetApplication:
    section: BudgetedPromptSection | None
    report: PromptSectionAssemblyReport


def _section_is_omitted_by_zero_budget(
    section: PromptSectionInput,
    max_chars: int,
    max_items: int,
) -> bool:
    return max_chars == 0 or (bool(section.items) and max_items == 0)


def _render_section_content(section: PromptSectionInput) -> str:
    if section.items:
        return _render_items(section.title, section.items)
    if not section.content.strip():
        return ""
    if section.kind is PromptSectionKind.USER_INPUT:
        return section.content
    return f"{section.title}:\n{section.content}"


def _render_items(title: str, items: tuple[str, ...]) -> str:
    return f"{title}:\n" + "\n".join(f"- {item}" for item in items)


def _items_after_item_budget(section: PromptSectionInput, max_items: int) -> tuple[str, ...]:
    if not section.items:
        return ()
    if len(section.items) > max_items > 0:
        return _items_kept_for_section(section.kind, section.items, max_items)
    return section.items


def _items_kept_for_section(
    kind: PromptSectionKind,
    items: tuple[str, ...],
    max_items: int,
) -> tuple[str, ...]:
    if max_items <= 0:
        return ()
    if kind is PromptSectionKind.RECENT_CONVERSATION:
        return items[-max_items:]
    return items[:max_items]


def _items_within_char_budget(
    kind: PromptSectionKind,
    title: str,
    items: tuple[str, ...],
    max_chars: int,
) -> tuple[str, ...]:
    if max_chars <= 0 or not items:
        return ()
    if len(_render_items(title, items)) <= max_chars:
        return items
    if kind is PromptSectionKind.RECENT_CONVERSATION:
        return _latest_items_within_char_budget(title, items, max_chars)
    return _first_items_within_char_budget(title, items, max_chars)


def _latest_items_within_char_budget(
    title: str,
    items: tuple[str, ...],
    max_chars: int,
) -> tuple[str, ...]:
    kept: tuple[str, ...] = ()
    for item in reversed(items):
        candidate = (item, *kept)
        if len(_render_items(title, candidate)) <= max_chars:
            kept = candidate
            continue
        if not kept:
            truncated = _truncate_item_to_fit(
                PromptSectionKind.RECENT_CONVERSATION,
                title,
                item,
                max_chars,
            )
            return (truncated,) if truncated is not None else ()
        break
    return kept


def _first_items_within_char_budget(
    title: str,
    items: tuple[str, ...],
    max_chars: int,
) -> tuple[str, ...]:
    kept: tuple[str, ...] = ()
    for item in items:
        candidate = (*kept, item)
        if len(_render_items(title, candidate)) <= max_chars:
            kept = candidate
            continue
        if not kept:
            truncated = _truncate_item_to_fit(PromptSectionKind.USER_MEMORY, title, item, max_chars)
            return (truncated,) if truncated is not None else ()
        break
    return kept


def _truncate_item_to_fit(
    kind: PromptSectionKind,
    title: str,
    item: str,
    max_chars: int,
) -> str | None:
    if kind is PromptSectionKind.RECENT_CONVERSATION:
        return _truncate_conversation_item_to_fit(title, item, max_chars)
    overhead = len(_render_items(title, ("",)))
    available = max_chars - overhead
    if available <= 0:
        return None
    return _truncate_text(item, available)


def _truncate_conversation_item_to_fit(
    title: str,
    item: str,
    max_chars: int,
) -> str | None:
    role_prefix, separator, content = item.partition(": ")
    if not separator:
        return None
    prefix = f"{role_prefix}{separator}"
    available = max_chars - len(_render_items(title, (prefix,)))
    if available <= 0:
        return None
    return f"{prefix}{_truncate_text(content, available)}"


def _truncate_text(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    marker = "…"
    if max_chars == 1:
        return marker
    return f"{text[: max_chars - 1]}{marker}"


def _input_item_count(section: PromptSectionInput) -> int:
    return len(section.items) if section.items else (1 if section.content else 0)


def _omitted_result(
    section: PromptSectionInput,
    budget: RuntimePromptSectionBudget,
    input_chars: int,
    input_items: int,
) -> _SectionBudgetApplication:
    report = PromptSectionAssemblyReport(
        kind=section.kind,
        trust_boundary=section.trust_boundary,
        input_chars=input_chars,
        output_chars=0,
        input_items=input_items,
        output_items=0,
        max_chars=budget.max_chars,
        max_items=budget.max_items,
        priority=budget.priority,
        overflow_behavior=budget.overflow_behavior,
        omitted=True,
        truncated_chars=input_chars,
        truncated_items=input_items,
    )
    return _SectionBudgetApplication(section=None, report=report)


def _overflow_sort_key(item: tuple[int, _SectionBudgetApplication]) -> tuple[int, int]:
    return item[1].report.priority, item[0]


def _omit_existing(result: _SectionBudgetApplication) -> _SectionBudgetApplication:
    current = result.report
    report = PromptSectionAssemblyReport(
        kind=current.kind,
        trust_boundary=current.trust_boundary,
        input_chars=current.input_chars,
        output_chars=0,
        input_items=current.input_items,
        output_items=0,
        max_chars=current.max_chars,
        max_items=current.max_items,
        priority=current.priority,
        overflow_behavior=current.overflow_behavior,
        omitted=True,
        truncated_chars=current.input_chars,
        truncated_items=current.input_items,
    )
    return _SectionBudgetApplication(section=None, report=report)


def _truncate_existing(
    result: _SectionBudgetApplication,
    max_chars: int,
) -> _SectionBudgetApplication:
    if result.section is None:
        return result
    if result.section.items:
        kept_items = _items_within_char_budget(
            result.section.kind,
            result.section.title,
            result.section.items,
            max_chars,
        )
        if not kept_items:
            return _omit_existing(result)
        return _replace_existing_with_items(result, kept_items)
    content = _truncate_text(result.section.content, max_chars)
    return _replace_existing_with_content(result, content)


def _replace_existing_with_items(
    result: _SectionBudgetApplication,
    kept_items: tuple[str, ...],
) -> _SectionBudgetApplication:
    if result.section is None:
        return result
    content = _render_items(result.section.title, kept_items)
    section = BudgetedPromptSection(
        kind=result.section.kind,
        title=result.section.title,
        trust_boundary=result.section.trust_boundary,
        content=content,
        items=kept_items,
    )
    current = result.report
    report = PromptSectionAssemblyReport(
        kind=current.kind,
        trust_boundary=current.trust_boundary,
        input_chars=current.input_chars,
        output_chars=len(content),
        input_items=current.input_items,
        output_items=len(kept_items),
        max_chars=current.max_chars,
        max_items=current.max_items,
        priority=current.priority,
        overflow_behavior=current.overflow_behavior,
        omitted=False,
        truncated_chars=max(current.input_chars - len(content), 0),
        truncated_items=max(current.input_items - len(kept_items), current.truncated_items),
    )
    return _SectionBudgetApplication(section=section, report=report)


def _replace_existing_with_content(
    result: _SectionBudgetApplication,
    content: str,
) -> _SectionBudgetApplication:
    if result.section is None:
        return result
    section = BudgetedPromptSection(
        kind=result.section.kind,
        title=result.section.title,
        trust_boundary=result.section.trust_boundary,
        content=content,
        items=(),
    )
    current = result.report
    report = PromptSectionAssemblyReport(
        kind=current.kind,
        trust_boundary=current.trust_boundary,
        input_chars=current.input_chars,
        output_chars=len(content),
        input_items=current.input_items,
        output_items=current.output_items,
        max_chars=current.max_chars,
        max_items=current.max_items,
        priority=current.priority,
        overflow_behavior=current.overflow_behavior,
        omitted=current.omitted,
        truncated_chars=max(current.input_chars - len(content), 0),
        truncated_items=current.truncated_items,
    )
    return _SectionBudgetApplication(section=section, report=report)
