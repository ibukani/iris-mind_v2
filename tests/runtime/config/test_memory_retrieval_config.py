"""Memory retrieval config tests。"""

from __future__ import annotations

import pytest

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.memory import RuntimeMemoryConfig, apply_memory_toml
from tests.helpers.approx import approx


def test_memory_retrieval_config_defaults_to_semantic_disabled() -> None:
    """Semantic retrieval は既存挙動維持のため default disabled。"""
    config = RuntimeMemoryConfig()

    assert config.retrieval.semantic_enabled is False
    assert config.retrieval.vector_limit == 20
    assert config.retrieval.reranker_limit == 5
    assert config.retrieval.duplicate_similarity_threshold == approx(0.98)


def test_apply_memory_toml_parses_retrieval_section() -> None:
    """[memory.retrieval] を typed runtime config に適用する。"""
    config = apply_memory_toml(
        RuntimeMemoryConfig(),
        {
            "retrieval": {
                "semantic_enabled": True,
                "fts_limit": 4,
                "vector_limit": 11,
                "candidate_limit": 7,
                "reranker_limit": 3,
                "min_score": 0.25,
                "duplicate_similarity_threshold": 0.91,
            }
        },
    )

    assert config.retrieval.semantic_enabled is True
    assert config.retrieval.fts_limit == 4
    assert config.retrieval.vector_limit == 11
    assert config.retrieval.candidate_limit == 7
    assert config.retrieval.reranker_limit == 3
    assert config.retrieval.min_score == approx(0.25)
    assert config.retrieval.duplicate_similarity_threshold == approx(0.91)


def test_apply_memory_toml_rejects_invalid_retrieval_threshold() -> None:
    """重複判定 threshold は 0.0 から 1.0 の範囲に制限する。"""
    with pytest.raises(ConfigError, match="duplicate_similarity_threshold"):
        apply_memory_toml(
            RuntimeMemoryConfig(),
            {"retrieval": {"duplicate_similarity_threshold": 1.5}},
        )
