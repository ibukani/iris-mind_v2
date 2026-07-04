"""Reranker retrieval contract tests。"""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from iris.contracts.model_invocation import ModelInvocationMetadata
from iris.contracts.model_policy import ModelCallKind
from iris.contracts.retrieval import RerankCandidate, RerankedItem, RerankRequest, RerankResult
from tests.helpers.approx import approx


def test_rerank_result_exposes_rank_score_metadata_and_latency() -> None:
    """Rerank result は candidate/score/rank/model metadata/latency を保持する。"""
    candidate = RerankCandidate(candidate_id="mem-1", text="green tea", base_score=0.2)
    item = RerankedItem(
        candidate=candidate,
        score=0.8,
        rank=1,
        reason="query overlap",
        model_metadata=_reranker_metadata(),
    )

    result = RerankResult(
        items=(item,),
        reason="reranked",
        model_metadata=_reranker_metadata(),
        latency_ms=9.0,
    )

    assert result.items[0].candidate.candidate_id == "mem-1"
    assert result.items[0].score == approx(0.8)
    assert result.items[0].rank == 1
    assert result.model_metadata.call_kind is ModelCallKind.RERANKER
    assert result.latency_ms == approx(9.0)


def test_rerank_contract_validates_candidate_id_rank_limit_and_latency() -> None:
    """空 candidate id、不正 rank、不正 limit、不正 latency は拒否される。"""
    candidate = RerankCandidate(candidate_id="mem-1", text="green tea")

    with pytest.raises(ValidationError):
        RerankCandidate(candidate_id=" ", text="green tea")

    with pytest.raises(ValidationError):
        RerankedItem(
            candidate=candidate,
            score=0.1,
            rank=0,
            reason="invalid rank",
            model_metadata=_reranker_metadata(),
        )

    with pytest.raises(ValidationError):
        RerankRequest(query="tea", candidates=(candidate,), limit=-1)

    with pytest.raises(ValidationError):
        RerankResult(
            items=(),
            reason="invalid latency",
            model_metadata=_reranker_metadata(),
            latency_ms=-1.0,
        )


def test_rerank_request_keeps_prompt_safe_metadata_only() -> None:
    """Request metadata は safe key/value だけを保持し、candidate text は resultに閉じる。"""
    request = RerankRequest(
        query="tea",
        candidates=(RerankCandidate(candidate_id="mem-1", text="green tea"),),
        limit=1,
        model_slot="memory_reranker",
        metadata={"feature": "memory_retrieval"},
    )

    assert request.limit == 1
    assert request.model_slot == "memory_reranker"
    assert request.metadata == {"feature": "memory_retrieval"}


def _reranker_metadata() -> ModelInvocationMetadata:
    return ModelInvocationMetadata(
        call_kind=ModelCallKind.RERANKER,
        provider="rule",
        model_name="rule-reranker-v1",
        adapter_name="rule_based_reranker",
    )
