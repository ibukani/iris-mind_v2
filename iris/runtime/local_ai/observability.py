"""小型モデル port 呼び出しの runtime observability wrapper。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.contracts.classification import (
    ClassificationRequest,
    ClassificationResult,
    classification_result_with_latency,
)
from iris.contracts.embeddings import (
    EmbeddingBatchRequest,
    EmbeddingBatchResult,
    EmbeddingRequest,
    EmbeddingResult,
    embedding_batch_result_with_latency,
    embedding_result_with_latency,
)
from iris.contracts.retrieval import RerankRequest, RerankResult, rerank_result_with_latency
from iris.runtime.observability.context import increment_trace_call
from iris.runtime.observability.ports import (
    RuntimeLatencyBudget,
    RuntimeLatencyStage,
    RuntimeModelCallKind,
)
from iris.runtime.observability.timing import RuntimeLatencyRecorder, latency_ms, perf_counter

if TYPE_CHECKING:
    from iris.contracts.classification import TextClassifier
    from iris.contracts.embeddings import EmbeddingClient
    from iris.contracts.retrieval import Reranker
    from iris.runtime.observability.ports import RuntimeObservationObserver


class ObservableTextClassifier:
    """TextClassifier 呼び出しを trace counter と latency event に接続する wrapper。"""

    def __init__(
        self,
        classifier: TextClassifier,
        observer: RuntimeObservationObserver | None,
        latency_budget: RuntimeLatencyBudget | None = None,
    ) -> None:
        """Classifier と runtime observer を注入する。"""
        self._classifier = classifier
        self._recorder = RuntimeLatencyRecorder(observer, latency_budget)

    def classify(self, request: ClassificationRequest) -> ClassificationResult:
        """分類器を呼び出し、classifier call count と latency を記録する。

        Returns:
            ClassificationResult: latency 付き分類結果。
        """
        increment_trace_call(RuntimeModelCallKind.CLASSIFIER)
        started_at = perf_counter()
        try:
            result = self._classifier.classify(request)
        except BaseException as exc:
            self._record_stage(started_at, error_type=type(exc).__name__)
            raise
        measured_latency_ms = latency_ms(started_at)
        self._record_stage(started_at, latency_ms_value=measured_latency_ms)
        return classification_result_with_latency(result, latency_ms=measured_latency_ms)

    def _record_stage(
        self,
        started_at: float,
        *,
        latency_ms_value: float | None = None,
        error_type: str | None = None,
    ) -> None:
        self._recorder.record_stage(
            RuntimeLatencyStage.CLASSIFIER_CALL,
            latency_ms=latency_ms_value or latency_ms(started_at),
            error_type=error_type,
        )


class ObservableEmbeddingClient:
    """EmbeddingClient 呼び出しを trace counter と latency event に接続する wrapper。"""

    def __init__(
        self,
        client: EmbeddingClient,
        observer: RuntimeObservationObserver | None,
        latency_budget: RuntimeLatencyBudget | None = None,
    ) -> None:
        """Embedding client と runtime observer を注入する。"""
        self._client = client
        self._recorder = RuntimeLatencyRecorder(observer, latency_budget)

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
        """単一 embedding 呼び出しの counter と latency を記録する。

        Returns:
            EmbeddingResult: latency 付き embedding 結果。
        """
        increment_trace_call(RuntimeModelCallKind.EMBEDDING)
        started_at = perf_counter()
        try:
            result = self._client.embed_text(request)
        except BaseException as exc:
            self._record_stage(started_at, error_type=type(exc).__name__)
            raise
        measured_latency_ms = latency_ms(started_at)
        self._record_stage(started_at, latency_ms_value=measured_latency_ms)
        return embedding_result_with_latency(result, latency_ms=measured_latency_ms)

    def embed_text_batch(self, request: EmbeddingBatchRequest) -> EmbeddingBatchResult:
        """Batch embedding 呼び出しの counter と latency を記録する。

        Returns:
            EmbeddingBatchResult: latency 付き batch embedding 結果。
        """
        increment_trace_call(RuntimeModelCallKind.EMBEDDING)
        started_at = perf_counter()
        try:
            result = self._client.embed_text_batch(request)
        except BaseException as exc:
            self._record_stage(started_at, error_type=type(exc).__name__)
            raise
        measured_latency_ms = latency_ms(started_at)
        self._record_stage(started_at, latency_ms_value=measured_latency_ms)
        return embedding_batch_result_with_latency(result, latency_ms=measured_latency_ms)

    def _record_stage(
        self,
        started_at: float,
        *,
        latency_ms_value: float | None = None,
        error_type: str | None = None,
    ) -> None:
        self._recorder.record_stage(
            RuntimeLatencyStage.EMBEDDING_CALL,
            latency_ms=latency_ms_value or latency_ms(started_at),
            error_type=error_type,
        )


class ObservableReranker:
    """Reranker 呼び出しを trace counter と latency event に接続する wrapper。"""

    def __init__(
        self,
        reranker: Reranker,
        observer: RuntimeObservationObserver | None,
        latency_budget: RuntimeLatencyBudget | None = None,
    ) -> None:
        """Reranker と runtime observer を注入する。"""
        self._reranker = reranker
        self._recorder = RuntimeLatencyRecorder(observer, latency_budget)

    def rerank(self, request: RerankRequest) -> RerankResult:
        """Reranker 呼び出しの counter と latency を記録する。

        Returns:
            RerankResult: latency 付き rerank 結果。
        """
        increment_trace_call(RuntimeModelCallKind.RERANKER)
        started_at = perf_counter()
        try:
            result = self._reranker.rerank(request)
        except BaseException as exc:
            self._record_stage(started_at, error_type=type(exc).__name__)
            raise
        measured_latency_ms = latency_ms(started_at)
        self._record_stage(started_at, latency_ms_value=measured_latency_ms)
        return rerank_result_with_latency(result, latency_ms=measured_latency_ms)

    def _record_stage(
        self,
        started_at: float,
        *,
        latency_ms_value: float | None = None,
        error_type: str | None = None,
    ) -> None:
        self._recorder.record_stage(
            RuntimeLatencyStage.RERANKER_CALL,
            latency_ms=latency_ms_value or latency_ms(started_at),
            error_type=error_type,
        )
