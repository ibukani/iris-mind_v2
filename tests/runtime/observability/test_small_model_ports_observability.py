"""小型モデル port の observability / budget wrapper tests。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from tests.helpers.approx import approx

if TYPE_CHECKING:
    from iris.runtime.observability.ports import RuntimeLogFields, RuntimeLogValue

from iris.adapters.classifiers.fake import FakeClassificationCase, FakeTextClassifier
from iris.adapters.embeddings.fake import DeterministicFakeEmbedding
from iris.adapters.rerankers.fake import FakeReranker
from iris.contracts.classification import ClassificationRequest, ClassificationResult
from iris.contracts.embeddings import (
    EmbeddingBatchRequest,
    EmbeddingBatchResult,
    EmbeddingRequest,
    EmbeddingResult,
)
from iris.contracts.retrieval import RerankCandidate, RerankRequest, RerankResult
from iris.runtime.config.model_call_budget import (
    RuntimeFeatureModelCallBudget,
    RuntimeModelCallBudgetConfig,
)
from iris.runtime.local_ai.budgeted import (
    BudgetedEmbeddingClient,
    BudgetedReranker,
    BudgetedTextClassifier,
)
from iris.runtime.local_ai.composition import (
    compose_observable_budgeted_embedding_client,
    compose_observable_budgeted_reranker,
    compose_observable_budgeted_text_classifier,
)
from iris.runtime.local_ai.observability import (
    ObservableEmbeddingClient,
    ObservableReranker,
    ObservableTextClassifier,
)
from iris.runtime.model_call_budget import bind_model_call_budget_scope
from iris.runtime.observability.context import (
    RuntimeTraceContext,
    bind_trace_context,
    trace_counter_extra,
)


class _RecordingObserver:
    """Runtime observation observer fake。"""

    def __init__(self) -> None:
        self.events: list[tuple[str, RuntimeLogFields]] = []

    def record(self, event: str, **fields: RuntimeLogValue) -> None:
        """Event を記録する。"""
        self.events.append((event, fields))


@dataclass
class _CountingTextClassifier:
    """Budget test 用の呼び出し回数付き classifier。"""

    calls: int = 0

    def classify(self, request: ClassificationRequest) -> ClassificationResult:
        """呼び出し回数を増やして fake result を返す。

        Returns:
            ClassificationResult: fake classification result。
        """
        self.calls += 1
        return FakeTextClassifier(
            (FakeClassificationCase(text=request.text, label="intent.chat", confidence=1.0),)
        ).classify(request)


@dataclass
class _CountingEmbeddingClient:
    """Budget test 用の呼び出し回数付き embedding client。"""

    calls: int = 0
    embedding: DeterministicFakeEmbedding = field(
        default_factory=lambda: DeterministicFakeEmbedding(dimension=4)
    )

    @property
    def provider(self) -> str:
        """Provider 識別子を返す。"""
        return self.embedding.provider

    @property
    def model_id(self) -> str:
        """モデル識別子を返す。"""
        return self.embedding.model_id

    @property
    def dimension(self) -> int:
        """Embedding dimension を返す。"""
        return self.embedding.dimension

    def embed_text(self, request: EmbeddingRequest) -> EmbeddingResult:
        """呼び出し回数を増やして fake embedding を返す。

        Returns:
            EmbeddingResult: fake embedding result。
        """
        self.calls += 1
        return self.embedding.embed_text(request)

    def embed_text_batch(self, request: EmbeddingBatchRequest) -> EmbeddingBatchResult:
        """呼び出し回数を増やして fake batch embedding を返す。

        Returns:
            EmbeddingBatchResult: fake batch embedding result。
        """
        self.calls += 1
        return self.embedding.embed_text_batch(request)


@dataclass
class _CountingReranker:
    """Budget test 用の呼び出し回数付き reranker。"""

    calls: int = 0

    def rerank(self, request: RerankRequest) -> RerankResult:
        """呼び出し回数を増やして fake rerank を返す。

        Returns:
            RerankResult: fake rerank result。
        """
        self.calls += 1
        return FakeReranker().rerank(request)


def test_observable_classifier_records_call_count_latency_and_safe_fields() -> None:
    """Classifier wrapper は call count と classifier_call latency を出す。"""
    observer = _RecordingObserver()
    classifier = ObservableTextClassifier(
        FakeTextClassifier(
            (FakeClassificationCase(text="secret user text", label="intent.chat", confidence=1.0),)
        ),
        observer,
    )

    with bind_trace_context(_trace_context()):
        result = classifier.classify(ClassificationRequest(text="secret user text"))
        counters = trace_counter_extra()

    assert result.label == "intent.chat"
    assert counters["classifier_call_count"] == 1
    assert _stage_names(observer) == {"classifier_call"}
    fields = observer.events[0][1]
    assert fields["classifier_call_count"] == 1
    assert fields["budget_exceeded"] is False
    assert "secret user text" not in repr(observer.events)


def test_observable_embedding_and_reranker_record_separate_counters() -> None:
    """Embedding/Reranker wrapper は別々の call counter と stage を記録する。"""
    observer = _RecordingObserver()
    embedding = ObservableEmbeddingClient(DeterministicFakeEmbedding(dimension=4), observer)
    reranker = ObservableReranker(FakeReranker({"a": 1.0}), observer)

    with bind_trace_context(_trace_context()):
        embedding_result = embedding.embed_text(EmbeddingRequest(text="green tea"))
        rerank_result = reranker.rerank(
            RerankRequest(
                query="green",
                candidates=(RerankCandidate(candidate_id="a", text="green tea"),),
            )
        )
        counters = trace_counter_extra()

    assert embedding_result.dimension == 4
    assert rerank_result.items[0].candidate.candidate_id == "a"
    assert counters["embedding_call_count"] == 1
    assert counters["reranker_call_count"] == 1
    assert _stage_names(observer) == {"embedding_call", "reranker_call"}


def test_budgeted_classifier_denial_returns_unknown_without_adapter_call() -> None:
    """Budget denial 時は classifier adapter を呼ばず unknown result を返す。"""
    classifier = _CountingTextClassifier()
    budgeted = BudgetedTextClassifier(classifier, _budget_config(small_classifier_max_calls=0))

    with bind_model_call_budget_scope():
        result = budgeted.classify(ClassificationRequest(text="hello"))

    assert classifier.calls == 0
    assert result.label == "unknown"
    assert result.fallback_applied is True
    assert result.model_metadata.provider == "budget"


def test_budgeted_embedding_denial_returns_zero_vector_without_adapter_call() -> None:
    """Budget denial 時は embedding adapter を呼ばず zero-vector fallback を返す。"""
    client = _CountingEmbeddingClient()
    budgeted = BudgetedEmbeddingClient(client, _budget_config(embedding_max_calls=0))

    with bind_model_call_budget_scope():
        result = budgeted.embed_text(EmbeddingRequest(text="green tea"))

    assert client.calls == 0
    assert result.vector == (0.0, 0.0, 0.0, 0.0)
    assert result.dimension == 4
    assert result.model_metadata.provider == "budget"


def test_budgeted_reranker_denial_preserves_order_and_limit_without_adapter_call() -> None:
    """Budget denial 時は reranker adapter を呼ばず入力順 fallback を返す。"""
    reranker = _CountingReranker()
    budgeted = BudgetedReranker(reranker, _budget_config(reranker_max_calls=0))

    with bind_model_call_budget_scope():
        result = budgeted.rerank(
            RerankRequest(
                query="green",
                candidates=(
                    RerankCandidate(candidate_id="a", text="green tea", base_score=0.2),
                    RerankCandidate(candidate_id="b", text="black coffee", base_score=0.9),
                ),
                limit=1,
            )
        )

    assert reranker.calls == 0
    assert tuple(item.candidate.candidate_id for item in result.items) == ("a",)
    assert result.items[0].score == approx(0.2)
    assert result.model_metadata.provider == "budget"


def _trace_context() -> RuntimeTraceContext:
    return RuntimeTraceContext(
        correlation_id="corr-small-model",
        observation_id="obs-small-model",
        observation_kind="actor_message",
        ingress_kind="external_client",
        adapter_id=None,
        provider=None,
        actor_id="actor-small-model",
        space_id="space-small-model",
    )


def _stage_names(observer: _RecordingObserver) -> set[str]:
    return {
        str(fields["stage"])
        for event, fields in observer.events
        if event == "runtime.latency.stage"
    }


def _budget_config(
    *,
    small_classifier_max_calls: int = 1,
    embedding_max_calls: int = 1,
    reranker_max_calls: int = 1,
) -> RuntimeModelCallBudgetConfig:
    return RuntimeModelCallBudgetConfig(
        user_response_hot_path=RuntimeFeatureModelCallBudget(
            small_classifier_max_calls=small_classifier_max_calls,
            embedding_max_calls=embedding_max_calls,
            reranker_max_calls=reranker_max_calls,
        )
    )


def test_composed_classifier_observes_budget_denial_without_adapter_call() -> None:
    """推奨合成は budget denial も classifier call として観測する。"""
    observer = _RecordingObserver()
    classifier = _CountingTextClassifier()
    composed = compose_observable_budgeted_text_classifier(
        classifier,
        observer,
        budget_config=_budget_config(small_classifier_max_calls=0),
    )

    with bind_model_call_budget_scope(), bind_trace_context(_trace_context()):
        result = composed.classify(ClassificationRequest(text="secret user text"))
        counters = trace_counter_extra()

    assert classifier.calls == 0
    assert result.label == "unknown"
    assert result.model_metadata.provider == "budget"
    assert counters["classifier_call_count"] == 1
    assert _stage_names(observer) == {"classifier_call"}
    assert "secret user text" not in repr(observer.events)


def test_composed_embedding_observes_budget_denial_without_adapter_call() -> None:
    """推奨合成は budget denial も embedding call として観測する。"""
    observer = _RecordingObserver()
    client = _CountingEmbeddingClient()
    composed = compose_observable_budgeted_embedding_client(
        client,
        observer,
        budget_config=_budget_config(embedding_max_calls=0),
    )

    with bind_model_call_budget_scope(), bind_trace_context(_trace_context()):
        result = composed.embed_text(EmbeddingRequest(text="secret query text"))
        counters = trace_counter_extra()

    assert client.calls == 0
    assert result.vector == (0.0, 0.0, 0.0, 0.0)
    assert result.model_metadata.provider == "budget"
    assert counters["embedding_call_count"] == 1
    assert _stage_names(observer) == {"embedding_call"}
    assert "secret query text" not in repr(observer.events)


def test_composed_reranker_observes_budget_denial_without_adapter_call() -> None:
    """推奨合成は budget denial も reranker call として観測する。"""
    observer = _RecordingObserver()
    reranker = _CountingReranker()
    composed = compose_observable_budgeted_reranker(
        reranker,
        observer,
        budget_config=_budget_config(reranker_max_calls=0),
    )

    with bind_model_call_budget_scope(), bind_trace_context(_trace_context()):
        result = composed.rerank(
            RerankRequest(
                query="secret query text",
                candidates=(RerankCandidate(candidate_id="a", text="secret candidate text"),),
            )
        )
        counters = trace_counter_extra()

    assert reranker.calls == 0
    assert tuple(item.candidate.candidate_id for item in result.items) == ("a",)
    assert result.model_metadata.provider == "budget"
    assert counters["reranker_call_count"] == 1
    assert _stage_names(observer) == {"reranker_call"}
    assert "secret query text" not in repr(observer.events)
    assert "secret candidate text" not in repr(observer.events)
