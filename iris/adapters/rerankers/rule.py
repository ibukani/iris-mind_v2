"""決定論的 rule-based reranker adapter。"""

from __future__ import annotations

from dataclasses import dataclass

from iris.contracts.model_invocation import ModelInvocationMetadata
from iris.contracts.model_policy import ModelCallKind
from iris.contracts.retrieval import RerankCandidate, RerankedItem, RerankRequest, RerankResult


@dataclass(frozen=True)
class _ScoredCandidate:
    candidate: RerankCandidate
    score: float
    original_index: int


class RuleBasedReranker:
    """Query と candidate text の token overlap で再順位付けする reranker。"""

    def __init__(self, *, model: str = "rule-reranker-v1") -> None:
        """モデル識別子を注入する。"""
        self._model = model

    def rerank(self, request: RerankRequest) -> RerankResult:
        """Token overlap と base_score を合算して候補を再順位付けする。

        Returns:
            RerankResult: token overlap による順位付け結果。
        """
        metadata = self._metadata_for_slot(request.model_slot)
        ranked = _limit_scored_candidates(
            tuple(
                sorted(
                    _score_candidates(request),
                    key=lambda item: (-item.score, item.original_index),
                )
            ),
            request.limit,
        )
        return RerankResult(
            items=tuple(
                _reranked_item(item, rank, metadata) for rank, item in enumerate(ranked, 1)
            ),
            reason="token overlap rerank",
            model_metadata=metadata,
            latency_ms=0.0,
        )

    def _metadata_for_slot(self, model_slot: str | None) -> ModelInvocationMetadata:
        return ModelInvocationMetadata(
            call_kind=ModelCallKind.RERANKER,
            provider="rule",
            model_name=self._model,
            adapter_name="rule_based_reranker",
            model_slot=model_slot,
        )


def _score_candidates(request: RerankRequest) -> tuple[_ScoredCandidate, ...]:
    query_tokens = _tokens(request.query)
    return tuple(
        _ScoredCandidate(
            candidate=candidate,
            score=candidate.base_score + _overlap_score(query_tokens, _tokens(candidate.text)),
            original_index=index,
        )
        for index, candidate in enumerate(request.candidates)
    )


def _tokens(text: str) -> frozenset[str]:
    return frozenset(token for token in text.casefold().split() if token)


def _overlap_score(query_tokens: frozenset[str], candidate_tokens: frozenset[str]) -> float:
    if not query_tokens or not candidate_tokens:
        return 0.0
    return len(query_tokens & candidate_tokens) / len(query_tokens)


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
        reason="token overlap plus base score",
        model_metadata=metadata,
        metadata=item.candidate.metadata,
    )
