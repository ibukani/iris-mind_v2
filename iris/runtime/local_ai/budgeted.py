"""小型モデル port を #88 model call budget gate に接続する wrapper。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.contracts.classification import ClassificationRequest, ClassificationResult
from iris.contracts.embeddings import (
    EmbeddingBatchRequest,
    EmbeddingBatchResult,
    EmbeddingRequest,
    EmbeddingResult,
)
from iris.contracts.model_invocation import ModelInvocationMetadata
from iris.contracts.model_policy import (
    CascadeResult,
    ModelCallDescriptor,
    ModelCallKind,
    ModelCallSite,
)
from iris.contracts.retrieval import RerankedItem, RerankRequest, RerankResult
from iris.runtime.model_call_budget import ModelCallBudgetGate

if TYPE_CHECKING:
    from iris.contracts.classification import TextClassifier
    from iris.contracts.embeddings import EmbeddingClient
    from iris.contracts.metadata import ImmutableMetadata
    from iris.contracts.retrieval import Reranker
    from iris.runtime.config.model_call_budget import RuntimeModelCallBudgetConfig


class BudgetedTextClassifier:
    """TextClassifier 呼び出し前に model call budget を検査する wrapper。"""

    def __init__(
        self,
        classifier: TextClassifier,
        config: RuntimeModelCallBudgetConfig | None = None,
        *,
        call_site: ModelCallSite = ModelCallSite.USER_RESPONSE_HOT_PATH,
    ) -> None:
        """Classifier、budget config、call site を注入する。"""
        self._classifier = classifier
        self._gate = ModelCallBudgetGate(config)
        self._call_site = call_site

    def classify(self, request: ClassificationRequest) -> ClassificationResult:
        """Budget が許可した場合だけ分類器を呼び出す。

        Returns:
            ClassificationResult: 実分類結果または budget fallback。
        """
        cascade = self._gate.check_and_record(
            ModelCallDescriptor(
                call_kind=ModelCallKind.SMALL_CLASSIFIER,
                call_site=self._call_site,
                model_slot=request.model_slot,
                confidence=1.0,
                metadata=request.metadata,
            )
        )
        if cascade.accepted:
            return self._classifier.classify(request)
        return ClassificationResult(
            label="unknown",
            confidence=0.0,
            reason=cascade.reason,
            model_metadata=_budget_metadata(
                call_kind=ModelCallKind.SMALL_CLASSIFIER,
                model_slot=request.model_slot,
                adapter_name="budgeted_text_classifier",
            ),
            latency_ms=0.0,
            fallback_applied=True,
        )


class BudgetedEmbeddingClient:
    """EmbeddingClient 呼び出し前に model call budget を検査する wrapper。"""

    def __init__(
        self,
        client: EmbeddingClient,
        config: RuntimeModelCallBudgetConfig | None = None,
        *,
        call_site: ModelCallSite = ModelCallSite.USER_RESPONSE_HOT_PATH,
    ) -> None:
        """Embedding client、budget config、call site を注入する。"""
        self._client = client
        self._gate = ModelCallBudgetGate(config)
        self._call_site = call_site

    @property
    def provider(self) -> str:
        """Provider 識別子を返す。"""
        return self._client.provider

    @property
    def model_id(self) -> str:
        """モデル識別子を返す。"""
        return self._client.model_id

    @property
    def dimension(self) -> int:
        """Embedding dimension を返す。"""
        return self._client.dimension

    def embed_text(self, request: EmbeddingRequest) -> EmbeddingResult:
        """Budget が許可した場合だけ単一 embedding を実行する。

        Returns:
            EmbeddingResult: 実 embedding または zero-vector fallback。
        """
        cascade = self._check_budget(request.model_slot, request.metadata)
        if cascade.accepted:
            return self._client.embed_text(request)
        return _zero_embedding_result(
            dimension=self.dimension,
            reason=cascade.reason,
            model_slot=request.model_slot,
        )

    def embed_text_batch(self, request: EmbeddingBatchRequest) -> EmbeddingBatchResult:
        """Budget が許可した場合だけ batch embedding を実行する。

        Returns:
            EmbeddingBatchResult: 実 batch embedding または zero-vector fallback。
        """
        cascade = self._check_budget(request.model_slot, request.metadata)
        if cascade.accepted:
            return self._client.embed_text_batch(request)
        metadata = _budget_metadata(
            call_kind=ModelCallKind.EMBEDDING,
            model_slot=request.model_slot,
            adapter_name="budgeted_embedding_client",
        )
        return EmbeddingBatchResult(
            embeddings=tuple(
                _zero_embedding_result_with_metadata(
                    dimension=self.dimension,
                    reason=cascade.reason,
                    metadata=metadata,
                )
                for _ in request.texts
            ),
            reason=cascade.reason,
            model_metadata=metadata,
            latency_ms=0.0,
            metadata=request.metadata,
        )

    def _check_budget(self, model_slot: str | None, metadata: ImmutableMetadata) -> CascadeResult:
        return self._gate.check_and_record(
            ModelCallDescriptor(
                call_kind=ModelCallKind.EMBEDDING,
                call_site=self._call_site,
                model_slot=model_slot,
                model_name=self.model_id,
                confidence=1.0,
                metadata=metadata,
            )
        )


class BudgetedReranker:
    """Reranker 呼び出し前に model call budget を検査する wrapper。"""

    def __init__(
        self,
        reranker: Reranker,
        config: RuntimeModelCallBudgetConfig | None = None,
        *,
        call_site: ModelCallSite = ModelCallSite.USER_RESPONSE_HOT_PATH,
    ) -> None:
        """Reranker、budget config、call site を注入する。"""
        self._reranker = reranker
        self._gate = ModelCallBudgetGate(config)
        self._call_site = call_site

    def rerank(self, request: RerankRequest) -> RerankResult:
        """Budget が許可した場合だけ reranker を呼び出す。

        Returns:
            RerankResult: 実 rerank 結果または入力順 fallback。
        """
        cascade = self._gate.check_and_record(
            ModelCallDescriptor(
                call_kind=ModelCallKind.RERANKER,
                call_site=self._call_site,
                model_slot=request.model_slot,
                confidence=1.0,
                metadata=request.metadata,
            )
        )
        if cascade.accepted:
            return self._reranker.rerank(request)
        metadata = _budget_metadata(
            call_kind=ModelCallKind.RERANKER,
            model_slot=request.model_slot,
            adapter_name="budgeted_reranker",
        )
        limited_candidates = (
            request.candidates if request.limit is None else request.candidates[: request.limit]
        )
        return RerankResult(
            items=tuple(
                RerankedItem(
                    candidate=candidate,
                    score=candidate.base_score,
                    rank=rank,
                    reason=cascade.reason,
                    model_metadata=metadata,
                    metadata=candidate.metadata,
                )
                for rank, candidate in enumerate(limited_candidates, 1)
            ),
            reason=cascade.reason,
            model_metadata=metadata,
            latency_ms=0.0,
            metadata=request.metadata,
        )


def _budget_metadata(
    *,
    call_kind: ModelCallKind,
    model_slot: str | None,
    adapter_name: str,
) -> ModelInvocationMetadata:
    return ModelInvocationMetadata(
        call_kind=call_kind,
        provider="budget",
        model_name="not_called",
        adapter_name=adapter_name,
        model_slot=model_slot,
    )


def _zero_embedding_result(
    *,
    dimension: int,
    reason: str,
    model_slot: str | None,
) -> EmbeddingResult:
    return _zero_embedding_result_with_metadata(
        dimension=dimension,
        reason=reason,
        metadata=_budget_metadata(
            call_kind=ModelCallKind.EMBEDDING,
            model_slot=model_slot,
            adapter_name="budgeted_embedding_client",
        ),
    )


def _zero_embedding_result_with_metadata(
    *,
    dimension: int,
    reason: str,
    metadata: ModelInvocationMetadata,
) -> EmbeddingResult:
    return EmbeddingResult(
        vector=tuple(0.0 for _ in range(dimension)),
        dimension=dimension,
        reason=reason,
        model_metadata=metadata,
        latency_ms=0.0,
    )
