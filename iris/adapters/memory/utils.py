"""Shared memory adapter utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.contracts.memory import MemoryRecord


def score_text_match(record: MemoryRecord, terms: tuple[str, ...]) -> int:
    """Count how many query terms appear in the record text.

    Args:
        record: Memory record to score.
        terms: Normalized (casefolded) search terms.

    Returns:
        Number of matching terms (0 if terms is empty).
    """
    if not terms:
        return 0
    text = record.text.casefold()
    return sum(1 for term in terms if term in text)
