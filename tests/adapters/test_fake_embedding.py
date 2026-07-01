"""DeterministicFakeEmbedding の契約テスト。"""

from __future__ import annotations

import pytest

from iris.adapters.embeddings.fake import DeterministicFakeEmbedding


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
