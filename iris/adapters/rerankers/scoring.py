"""決定論的 reranker adapter 共通の scoring primitives。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.retrieval import RerankCandidate, RerankedItem

if TYPE_CHECKING:
    from iris.contracts.model_invocation import ModelInvocationMetadata


@dataclass(frozen=True)
class ScoredCandidate:
    """安定 sort に必要な候補、score、元位置。"""

    candidate: RerankCandidate
    score: float
    original_index: int


def rank_scored_candidates(
    items: tuple[ScoredCandidate, ...],
    limit: int | None,
) -> tuple[ScoredCandidate, ...]:
    """Score 降順、元位置昇順で並べ、optional limit を適用する。

    Returns:
        安定順序かつ上限適用済みの候補。
    """
    ranked = tuple(sorted(items, key=lambda item: (-item.score, item.original_index)))
    if limit is None:
        return ranked
    return ranked[:limit]


def build_reranked_items(
    items: tuple[ScoredCandidate, ...],
    *,
    metadata: ModelInvocationMetadata,
    reason: str,
) -> tuple[RerankedItem, ...]:
    """順位付け済み候補を typed rerank result items へ変換する。

    Returns:
        1-origin rank と共通 metadata を持つ items。
    """
    return tuple(
        RerankedItem(
            candidate=item.candidate,
            score=item.score,
            rank=rank,
            reason=reason,
            model_metadata=metadata,
            metadata=item.candidate.metadata,
        )
        for rank, item in enumerate(items, 1)
    )
