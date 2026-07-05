"""Reranker retrieval contract tests。"""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from iris.contracts.model_invocation import ModelInvocationMetadata
from iris.contracts.model_policy import ModelCallKind
from iris.contracts.retrieval import (
    RerankCandidate,
    RerankedItem,
    RerankRequest,
    RerankResult,
    RetrievalCandidate,
    RetrievalFallbackReason,
    RetrievalPipelineObservation,
    RetrievalPipelineRequest,
    RetrievalPipelineResult,
    RetrievalSelectedItem,
    RetrievalSource,
    RetrievalSourceKind,
)
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


def test_retrieval_pipeline_result_exposes_source_score_reason_and_model_metadata() -> None:
    """#94 retrieval result は source ID/score/reason/model metadata を保持する。"""
    item = RetrievalSelectedItem(
        source_id="mem-1",
        source_kind=RetrievalSourceKind.MEMORY,
        text="User likes green tea.",
        score=0.91,
        rank=1,
        reason="fixed fake score",
        model_metadata=_reranker_metadata(),
    )

    result = RetrievalPipelineResult(
        items=(item,),
        fallback_reason=RetrievalFallbackReason.NONE,
        candidate_count=3,
        selected_count=1,
        dropped_duplicate_count=1,
        cache_hit_count=2,
        embedding_latency_ms=4.0,
        reranking_latency_ms=5.0,
    )

    assert result.items[0].source_id == "mem-1"
    assert result.items[0].source_kind is RetrievalSourceKind.MEMORY
    assert result.items[0].score == approx(0.91)
    assert result.items[0].reason == "fixed fake score"
    assert result.items[0].model_metadata.call_kind is ModelCallKind.RERANKER
    assert result.candidate_count == 3
    assert result.selected_count == 1
    assert result.dropped_duplicate_count == 1
    assert result.cache_hit_count == 2


def test_retrieval_source_contract_supports_future_context_sources() -> None:
    """Memory/project context/transcript source は同じ candidate contract を返せる。"""
    source: RetrievalSource = _StaticRetrievalSource(RetrievalSourceKind.PROJECT_CONTEXT)

    candidates = source.candidates(
        RetrievalPipelineRequest(
            query="persona",
            source_kinds=(RetrievalSourceKind.PROJECT_CONTEXT,),
            candidate_limit=1,
        )
    )

    assert source.source_kind is RetrievalSourceKind.PROJECT_CONTEXT
    assert candidates[0].source_kind is RetrievalSourceKind.PROJECT_CONTEXT
    assert candidates[0].source_id == "project-context-1"


def test_retrieval_pipeline_observation_omits_raw_text_fields() -> None:
    """Observability contract は raw query / memory text を持たない。"""
    observation = RetrievalPipelineObservation(
        candidate_count=3,
        selected_count=1,
        cache_hit_count=2,
        embedding_provider="test",
        embedding_model="keyword-v1",
        reranker_provider="fake",
        reranker_model="fake-reranker-v1",
    )

    dumped = observation.model_dump_json()
    assert "query" not in dumped
    assert "text" not in dumped
    assert observation.candidate_count == 3
    assert observation.selected_count == 1


def _reranker_metadata() -> ModelInvocationMetadata:
    return ModelInvocationMetadata(
        call_kind=ModelCallKind.RERANKER,
        provider="rule",
        model_name="rule-reranker-v1",
        adapter_name="rule_based_reranker",
    )


class _StaticRetrievalSource:
    """RetrievalSource Protocol 実装確認用の固定 source。"""

    def __init__(self, source_kind: RetrievalSourceKind) -> None:
        """返す source kind を保持する。"""
        self._source_kind = source_kind

    @property
    def source_kind(self) -> RetrievalSourceKind:
        """この source の種別。"""
        return self._source_kind

    def candidates(self, request: RetrievalPipelineRequest) -> tuple[RetrievalCandidate, ...]:
        """要求された上限に従い固定候補を返す。

        Returns:
            tuple[RetrievalCandidate, ...]: 固定候補。
        """
        if self._source_kind not in request.source_kinds or request.candidate_limit <= 0:
            return ()
        return (
            RetrievalCandidate(
                source_id="project-context-1",
                source_kind=self._source_kind,
                text="Project context summary",
                base_score=0.5,
                reason="static test candidate",
            ),
        )
