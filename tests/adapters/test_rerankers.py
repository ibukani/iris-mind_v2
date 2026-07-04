"""Reranker adapter tests。"""

from __future__ import annotations

from iris.adapters.rerankers.fake import FakeReranker
from iris.adapters.rerankers.rule import RuleBasedReranker
from iris.contracts.model_policy import ModelCallKind
from iris.contracts.retrieval import RerankCandidate, RerankRequest
from tests.helpers.approx import approx


def test_fake_reranker_orders_by_fixed_scores_and_limit() -> None:
    """FakeReranker は固定 score の降順で候補を返す。"""
    reranker = FakeReranker({"b": 0.9, "a": 0.1, "c": 0.5})

    result = reranker.rerank(
        RerankRequest(
            query="tea",
            candidates=(
                RerankCandidate(candidate_id="a", text="first"),
                RerankCandidate(candidate_id="b", text="second"),
                RerankCandidate(candidate_id="c", text="third"),
            ),
            limit=2,
            model_slot="memory_reranker",
        )
    )

    assert tuple(item.candidate.candidate_id for item in result.items) == ("b", "c")
    assert tuple(item.rank for item in result.items) == (1, 2)
    assert result.items[0].score == approx(0.9)
    assert result.model_metadata.call_kind is ModelCallKind.RERANKER
    assert result.model_metadata.provider == "fake"
    assert result.model_metadata.model_slot == "memory_reranker"


def test_rule_based_reranker_uses_token_overlap_and_stable_ties() -> None:
    """RuleBasedReranker は token overlap と base_score で安定順位を返す。"""
    reranker = RuleBasedReranker()

    result = reranker.rerank(
        RerankRequest(
            query="green tea",
            candidates=(
                RerankCandidate(candidate_id="a", text="green tea", base_score=0.1),
                RerankCandidate(candidate_id="b", text="green", base_score=0.1),
                RerankCandidate(candidate_id="c", text="coffee", base_score=0.9),
            ),
        )
    )

    assert tuple(item.candidate.candidate_id for item in result.items) == ("a", "c", "b")
    assert result.items[0].score == approx(1.1)
    assert result.items[1].score == approx(0.9)
    assert result.items[2].score == approx(0.6)
    assert result.model_metadata.provider == "rule"


def test_rule_based_reranker_limit_zero_returns_empty_items() -> None:
    """limit=0 は候補を呼び出し成功のまま空にする。"""
    reranker = RuleBasedReranker()

    result = reranker.rerank(
        RerankRequest(
            query="green tea",
            candidates=(RerankCandidate(candidate_id="a", text="green tea"),),
            limit=0,
        )
    )

    assert result.items == ()
    assert result.reason == "token overlap rerank"
