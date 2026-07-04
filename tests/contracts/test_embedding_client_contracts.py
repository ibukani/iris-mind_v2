"""EmbeddingClient contract tests。"""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from iris.contracts.embeddings import EmbeddingBatchResult, EmbeddingResult
from iris.contracts.model_invocation import ModelInvocationMetadata
from iris.contracts.model_policy import ModelCallKind
from tests.helpers.approx import approx


def test_embedding_result_exposes_vector_metadata_and_latency() -> None:
    """Embedding result は vector/dimension/model metadata/latency を保持する。"""
    result = EmbeddingResult(
        vector=(0.1, 0.2),
        dimension=2,
        reason="embedded",
        model_metadata=_embedding_metadata(),
        latency_ms=7.5,
    )

    assert result.vector == (0.1, 0.2)
    assert result.dimension == 2
    assert result.model_metadata.call_kind is ModelCallKind.EMBEDDING
    assert result.model_metadata.provider == "fake"
    assert result.latency_ms == approx(7.5)


def test_embedding_result_validates_dimension_and_latency() -> None:
    """非正 dimension と負 latency は拒否される。"""
    with pytest.raises(ValidationError):
        EmbeddingResult(
            vector=(),
            dimension=0,
            reason="invalid",
            model_metadata=_embedding_metadata(),
        )

    with pytest.raises(ValidationError):
        EmbeddingResult(
            vector=(0.0,),
            dimension=1,
            reason="invalid",
            model_metadata=_embedding_metadata(),
            latency_ms=-0.1,
        )


def test_embedding_batch_result_preserves_input_order_contract() -> None:
    """Batch result は embeddings tuple を順序付き contract として保持する。"""
    first = EmbeddingResult(
        vector=(1.0, 0.0),
        dimension=2,
        reason="first",
        model_metadata=_embedding_metadata(),
    )
    second = EmbeddingResult(
        vector=(0.0, 1.0),
        dimension=2,
        reason="second",
        model_metadata=_embedding_metadata(),
    )

    batch = EmbeddingBatchResult(
        embeddings=(first, second),
        reason="batch",
        model_metadata=_embedding_metadata(),
        latency_ms=2.0,
    )

    assert batch.embeddings == (first, second)
    assert batch.latency_ms == approx(2.0)


def _embedding_metadata() -> ModelInvocationMetadata:
    return ModelInvocationMetadata(
        call_kind=ModelCallKind.EMBEDDING,
        provider="fake",
        model_name="fake-v1",
        adapter_name="deterministic_fake_embedding",
    )
