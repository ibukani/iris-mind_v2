"""DeterministicFakeEmbedding の契約テスト。"""

from __future__ import annotations

import pytest

from iris.adapters.embeddings.fake import DeterministicFakeEmbedding
from iris.contracts.embeddings import EmbeddingBatchRequest, EmbeddingRequest
from tests.helpers.approx import approx


def test_fake_embedding_exposes_identity_and_is_deterministic() -> None:
    """Provider/model/dimension と同一入力の安定性を保証する。"""
    embedding = DeterministicFakeEmbedding(model="fake-test", dimension=8)

    first = embedding.embed("green tea")
    second = embedding.embed("green tea")

    assert embedding.provider == "fake"
    assert embedding.model_id == "fake-test"
    assert embedding.dimension == 8
    assert first == second
    assert len(first) == 8


def test_fake_embedding_rejects_invalid_dimension() -> None:
    """非正次元は初期化時に拒否する。"""
    with pytest.raises(ValueError, match="dimension"):
        DeterministicFakeEmbedding(dimension=0)


def test_fake_embedding_client_contract_result_is_deterministic() -> None:
    """EmbeddingClient contract の result も決定論的 metadata を返す。"""
    embedding = DeterministicFakeEmbedding(model="fake-test", dimension=8)

    first = embedding.embed_text(EmbeddingRequest(text="green tea", model_slot="memory_embedding"))
    second = embedding.embed_text(EmbeddingRequest(text="green tea", model_slot="memory_embedding"))

    assert first == second
    assert first.vector == embedding.embed("green tea")
    assert first.dimension == 8
    assert first.model_metadata.provider == "fake"
    assert first.model_metadata.model_name == "fake-test"
    assert first.model_metadata.model_slot == "memory_embedding"


def test_fake_embedding_client_batch_preserves_input_order() -> None:
    """Batch embedding result は入力順を保持する。"""
    embedding = DeterministicFakeEmbedding(model="fake-test", dimension=8)

    result = embedding.embed_text_batch(EmbeddingBatchRequest(texts=("green tea", "black coffee")))

    assert tuple(item.vector for item in result.embeddings) == embedding.embed_batch(
        ("green tea", "black coffee")
    )
    assert result.model_metadata.provider == "fake"
    assert result.latency_ms == approx(0.0)
