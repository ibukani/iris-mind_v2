"""テスト・開発用の決定論的 reranker adapter。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.model_invocation import ModelInvocationMetadata
from iris.contracts.model_policy import ModelCallKind
from iris.contracts.retrieval import RerankCandidate, RerankedItem, RerankRequest, RerankResult

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True)
class _ScoredCandidate:
    candidate: RerankCandidate
    score: float
    original_index: int


class FakeReranker:
    """候補 ID ごとの固定 score で再順位付けする reranker。"""

    def __init__(
        self,
        scores: Mapping[str, float] | None = None,
        *,
        model: str = "fake-reranker-v1",
    ) -> None:
        """固定 score table とモデル識別子を注入する。"""
        self._scores = dict(scores or {})
        self._model = model

    def rerank(self, request: RerankRequest) -> RerankResult:
        """固定 score table を使い、未定義候補は base_score で順位付けする。

        Returns:
            RerankResult: 固定 score による順位付け結果。
        """
        metadata = self._metadata_for_slot(request.model_slot)
        ranked = _limit_scored_candidates(
            tuple(
                sorted(
                    self._score_candidates(request),
                    key=lambda item: (-item.score, item.original_index),
                )
            ),
            request.limit,
        )
        return RerankResult(
            items=tuple(
                _reranked_item(item, rank, metadata) for rank, item in enumerate(ranked, 1)
            ),
            reason="fixed fake score rerank",
            model_metadata=metadata,
            latency_ms=0.0,
        )

    def _score_candidates(self, request: RerankRequest) -> tuple[_ScoredCandidate, ...]:
        return tuple(
            _ScoredCandidate(
                candidate=candidate,
                score=self._scores.get(candidate.candidate_id, candidate.base_score),
                original_index=index,
            )
            for index, candidate in enumerate(request.candidates)
        )

    def _metadata_for_slot(self, model_slot: str | None) -> ModelInvocationMetadata:
        return ModelInvocationMetadata(
            call_kind=ModelCallKind.RERANKER,
            provider="fake",
            model_name=self._model,
            adapter_name="fake_reranker",
            model_slot=model_slot,
        )


def _limit_scored_candidates(
    items: tuple[_ScoredCandidate, ...],
    limit: int | None,
) -> tuple[_ScoredCandidate, ...]:
    if limit is None:
        return items
    return items[:limit]


def _reranked_item(
    item: _ScoredCandidate,
    rank: int,
    metadata: ModelInvocationMetadata,
) -> RerankedItem:
    return RerankedItem(
        candidate=item.candidate,
        score=item.score,
        rank=rank,
        reason="fixed fake score",
        model_metadata=metadata,
        metadata=item.candidate.metadata,
    )
