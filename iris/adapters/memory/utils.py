"""Shared memory adapter utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.contracts.memory import MemorySearchResult

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.contracts.memory import MemoryQuery, MemoryRecord


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


def matches_query(record: MemoryRecord, query: MemoryQuery) -> bool:
    """Return whether a record satisfies all non-None filters in a query.

    Args:
        record: Memory record to evaluate.
        query: Query with optional actor_id, space_id, kind, and archived filters.

    Returns:
        True if the record matches all active filter criteria.
    """
    return (
        (query.include_archived or not record.archived)
        and (query.actor_id is None or record.actor_id == query.actor_id)
        and (query.space_id is None or record.space_id == query.space_id)
        and (query.kind is None or record.kind == query.kind)
    )


def rank_text_matches(
    eligible: Sequence[MemoryRecord],
    query: MemoryQuery,
) -> Sequence[MemorySearchResult]:
    """Rank eligible records by token overlap with the query text.

    Args:
        eligible: Records already matching scope filters.
        query: Search query with text and limit.

    Returns:
        Score-descending search results up to query.limit.
    """
    if query.limit <= 0:
        return ()

    terms = tuple(term.casefold() for term in query.text.split() if term.strip())
    ranked: list[tuple[int, int, MemorySearchResult]] = []
    for index, record in enumerate(eligible):
        score = score_text_match(record, terms)
        if score <= 0:
            continue
        ranked.append((score, index, MemorySearchResult(record=record, score=float(score))))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return tuple(result for _, _, result in ranked[: query.limit])
