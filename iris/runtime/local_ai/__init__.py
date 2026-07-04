"""小型モデル port の runtime 境界 wrapper。"""

from __future__ import annotations

from iris.runtime.local_ai.composition import (
    compose_observable_budgeted_embedding_client,
    compose_observable_budgeted_reranker,
    compose_observable_budgeted_text_classifier,
)

__all__ = (
    "compose_observable_budgeted_embedding_client",
    "compose_observable_budgeted_reranker",
    "compose_observable_budgeted_text_classifier",
)
