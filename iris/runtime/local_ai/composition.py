"""小型モデル port の推奨 wrapper 合成順序。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.contracts.model_policy import ModelCallSite
from iris.runtime.local_ai.budgeted import (
    BudgetedEmbeddingClient,
    BudgetedReranker,
    BudgetedTextClassifier,
)
from iris.runtime.local_ai.observability import (
    ObservableEmbeddingClient,
    ObservableReranker,
    ObservableTextClassifier,
)

if TYPE_CHECKING:
    from iris.contracts.classification import TextClassifier
    from iris.contracts.embeddings import EmbeddingClient
    from iris.contracts.retrieval import Reranker
    from iris.runtime.config.model_call_budget import RuntimeModelCallBudgetConfig
    from iris.runtime.observability.ports import (
        RuntimeLatencyBudget,
        RuntimeObservationObserver,
    )


def compose_observable_budgeted_text_classifier(
    classifier: TextClassifier,
    observer: RuntimeObservationObserver | None,
    *,
    budget_config: RuntimeModelCallBudgetConfig | None = None,
    latency_budget: RuntimeLatencyBudget | None = None,
    call_site: ModelCallSite = ModelCallSite.USER_RESPONSE_HOT_PATH,
) -> TextClassifier:
    """TextClassifier を `Observable(Budgeted(adapter))` の順序で合成する。

    Budget denial も classifier latency / call count として観測するため、
    observability wrapper を最外層に置く。

    Returns:
        TextClassifier: budget と observability が適用された classifier port。
    """
    return ObservableTextClassifier(
        BudgetedTextClassifier(classifier, budget_config, call_site=call_site),
        observer,
        latency_budget,
    )


def compose_observable_budgeted_embedding_client(
    client: EmbeddingClient,
    observer: RuntimeObservationObserver | None,
    *,
    budget_config: RuntimeModelCallBudgetConfig | None = None,
    latency_budget: RuntimeLatencyBudget | None = None,
    call_site: ModelCallSite = ModelCallSite.USER_RESPONSE_HOT_PATH,
) -> EmbeddingClient:
    """EmbeddingClient を `Observable(Budgeted(adapter))` の順序で合成する。

    Budget denial も embedding latency / call count として観測するため、
    observability wrapper を最外層に置く。

    Returns:
        EmbeddingClient: budget と observability が適用された embedding port。
    """
    return ObservableEmbeddingClient(
        BudgetedEmbeddingClient(client, budget_config, call_site=call_site),
        observer,
        latency_budget,
    )


def compose_observable_budgeted_reranker(
    reranker: Reranker,
    observer: RuntimeObservationObserver | None,
    *,
    budget_config: RuntimeModelCallBudgetConfig | None = None,
    latency_budget: RuntimeLatencyBudget | None = None,
    call_site: ModelCallSite = ModelCallSite.USER_RESPONSE_HOT_PATH,
) -> Reranker:
    """Reranker を `Observable(Budgeted(adapter))` の順序で合成する。

    Budget denial も reranker latency / call count として観測するため、
    observability wrapper を最外層に置く。

    Returns:
        Reranker: budget と observability が適用された reranker port。
    """
    return ObservableReranker(
        BudgetedReranker(reranker, budget_config, call_site=call_site),
        observer,
        latency_budget,
    )
