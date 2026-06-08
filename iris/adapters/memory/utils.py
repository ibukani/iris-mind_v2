"""Shared memory adapter utilities."""

from __future__ import annotations

from math import isclose, sqrt
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


_ERR_EMPTY_EMBEDDING = "Embedding function must return at least one dimension."
_ERR_DIMENSION_MISMATCH = "Vectors must have the same number of dimensions."


def vector_from_embedding(values: Sequence[float]) -> tuple[float, ...]:
    """Embedding 値を検証し tuple[float, ...] に変換する。

    Args:
        values: 埋め込み関数から返された float シーケンス。

    Returns:
        tuple[float, ...]: 検証済みベクトル。

    Raises:
        ValueError: ベクトルが空の場合。
    """
    vector = tuple(float(value) for value in values)
    if not vector:
        raise ValueError(_ERR_EMPTY_EMBEDDING)
    return vector


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    """2 つのベクトル間のコサイン類似度を計算する。

    Args:
        left: 左辺ベクトル。
        right: 右辺ベクトル。

    Returns:
        float: コサイン類似度 (範囲 -1.0 ~ 1.0)。いずれかのノルムが 0 の場合は 0.0。

    Raises:
        ValueError: ベクトル次元が一致しない場合。
    """
    if len(left) != len(right):
        raise ValueError(_ERR_DIMENSION_MISMATCH)

    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if isclose(left_norm, 0.0) or isclose(right_norm, 0.0):
        return 0.0

    dot_product = sum(
        left_value * right_value for left_value, right_value in zip(left, right, strict=True)
    )
    return dot_product / (left_norm * right_norm)
