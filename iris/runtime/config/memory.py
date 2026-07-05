"""Memory vector index と embedding のランタイム設定。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
import os
from typing import TYPE_CHECKING

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.parsing import (
    TomlTable,
    TomlValue,
    parse_bool,
    parse_float,
    parse_int,
    parse_optional_string,
    parse_string,
    table_or_empty,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


class MemoryVectorBackend(StrEnum):
    """利用可能な vector index backend。"""

    IN_MEMORY = "in_memory"
    QDRANT = "qdrant"


class MemoryEmbeddingProvider(StrEnum):
    """利用可能な embedding provider。"""

    FAKE = "fake"


@dataclass(frozen=True)
class RuntimeMemoryVectorQdrantConfig:
    """Qdrant 接続設定。"""

    url: str = "http://localhost:6333"
    api_key_env: str | None = None
    prefer_grpc: bool = False


@dataclass(frozen=True)
class RuntimeMemoryVectorConfig:
    """派生 vector index 設定。"""

    enabled: bool = False
    backend: MemoryVectorBackend = MemoryVectorBackend.IN_MEMORY
    collection: str = "iris_memory"
    rebuild_on_startup: bool = True
    fail_open_on_index_error: bool = True
    qdrant: RuntimeMemoryVectorQdrantConfig = RuntimeMemoryVectorQdrantConfig()


@dataclass(frozen=True)
class RuntimeMemoryEmbeddingConfig:
    """memory embedding 設定。"""

    provider: MemoryEmbeddingProvider = MemoryEmbeddingProvider.FAKE
    model: str = "fake-v1"
    dimension: int = 32
    batch_size: int = 32


@dataclass(frozen=True)
class RuntimeMemoryRetrievalConfig:
    """memory retrieval pipeline の hot-path 制御設定。"""

    semantic_enabled: bool = False
    fts_limit: int = 10
    vector_limit: int = 20
    candidate_limit: int = 20
    reranker_limit: int = 5
    min_score: float = 0.0
    duplicate_similarity_threshold: float = 0.98


@dataclass(frozen=True)
class RuntimeMemoryConfig:
    """memory retrieval 全体の設定。"""

    vector: RuntimeMemoryVectorConfig = RuntimeMemoryVectorConfig()
    embedding: RuntimeMemoryEmbeddingConfig = RuntimeMemoryEmbeddingConfig()
    retrieval: RuntimeMemoryRetrievalConfig = RuntimeMemoryRetrievalConfig()


def resolve_qdrant_api_key(
    config: RuntimeMemoryVectorQdrantConfig,
    *,
    env: Mapping[str, str] | None = None,
) -> str | None:
    """設定された環境変数名から Qdrant API key を解決する。

    Returns:
        API key。環境変数名が未指定または値がない場合は None。
    """
    source = os.environ if env is None else env
    return source.get(config.api_key_env) if config.api_key_env else None


def apply_memory_toml(config: RuntimeMemoryConfig, table: TomlTable) -> RuntimeMemoryConfig:
    """Memory TOML table を型付き設定へ適用する。

    Returns:
        更新済み memory 設定。
    """
    vector_table = table_or_empty(table, "vector", path="memory.vector")
    embedding_table = table_or_empty(table, "embedding", path="memory.embedding")
    qdrant_table = table_or_empty(vector_table, "qdrant", path="memory.vector.qdrant")
    retrieval_table = table_or_empty(table, "retrieval", path="memory.retrieval")
    qdrant = replace(
        config.vector.qdrant,
        url=parse_string(qdrant_table.get("url"), "memory.vector.qdrant.url")
        if "url" in qdrant_table
        else config.vector.qdrant.url,
        api_key_env=parse_optional_string(
            qdrant_table.get("api_key_env"), "memory.vector.qdrant.api_key_env"
        )
        if "api_key_env" in qdrant_table
        else config.vector.qdrant.api_key_env,
        prefer_grpc=parse_bool(qdrant_table.get("prefer_grpc"), "memory.vector.qdrant.prefer_grpc")
        if "prefer_grpc" in qdrant_table
        else config.vector.qdrant.prefer_grpc,
    )
    vector = replace(
        config.vector,
        enabled=_bool_value(vector_table, "enabled", default=config.vector.enabled),
        backend=_vector_backend(vector_table.get("backend", config.vector.backend)),
        collection=_string_value(vector_table, "collection", config.vector.collection),
        rebuild_on_startup=_bool_value(
            vector_table, "rebuild_on_startup", default=config.vector.rebuild_on_startup
        ),
        fail_open_on_index_error=_bool_value(
            vector_table,
            "fail_open_on_index_error",
            default=config.vector.fail_open_on_index_error,
        ),
        qdrant=qdrant,
    )
    embedding = replace(
        config.embedding,
        provider=_embedding_provider(embedding_table.get("provider", config.embedding.provider)),
        model=_string_value(embedding_table, "model", config.embedding.model),
        dimension=_int_value(embedding_table, "dimension", config.embedding.dimension),
        batch_size=_int_value(embedding_table, "batch_size", config.embedding.batch_size),
    )
    retrieval = replace(
        config.retrieval,
        semantic_enabled=_retrieval_bool_value(
            retrieval_table, "semantic_enabled", default=config.retrieval.semantic_enabled
        ),
        fts_limit=_retrieval_int_value(retrieval_table, "fts_limit", config.retrieval.fts_limit),
        vector_limit=_retrieval_int_value(
            retrieval_table, "vector_limit", config.retrieval.vector_limit
        ),
        candidate_limit=_retrieval_int_value(
            retrieval_table, "candidate_limit", config.retrieval.candidate_limit
        ),
        reranker_limit=_retrieval_int_value(
            retrieval_table, "reranker_limit", config.retrieval.reranker_limit
        ),
        min_score=_retrieval_float_value(retrieval_table, "min_score", config.retrieval.min_score),
        duplicate_similarity_threshold=_retrieval_float_value(
            retrieval_table,
            "duplicate_similarity_threshold",
            config.retrieval.duplicate_similarity_threshold,
        ),
    )
    _validate_embedding_config(embedding)
    _validate_retrieval_config(retrieval)
    return RuntimeMemoryConfig(vector=vector, embedding=embedding, retrieval=retrieval)


def _bool_value(table: TomlTable, key: str, *, default: bool) -> bool:
    return parse_bool(table[key], f"memory.vector.{key}") if key in table else default


def _retrieval_bool_value(table: TomlTable, key: str, *, default: bool) -> bool:
    return parse_bool(table[key], f"memory.retrieval.{key}") if key in table else default


def _string_value(table: TomlTable, key: str, default: str) -> str:
    return parse_string(table[key], f"memory.{key}") if key in table else default


def _int_value(table: TomlTable, key: str, default: int) -> int:
    return parse_int(table[key], f"memory.embedding.{key}") if key in table else default


def _retrieval_int_value(table: TomlTable, key: str, default: int) -> int:
    return parse_int(table[key], f"memory.retrieval.{key}") if key in table else default


def _retrieval_float_value(table: TomlTable, key: str, default: float) -> float:
    return parse_float(table[key], f"memory.retrieval.{key}") if key in table else default


def _vector_backend(value: TomlValue) -> MemoryVectorBackend:
    try:
        return MemoryVectorBackend(str(value))
    except ValueError as exc:
        message = "memory.vector.backend must be 'in_memory' or 'qdrant'"
        raise ConfigError(message) from exc


def _embedding_provider(value: TomlValue) -> MemoryEmbeddingProvider:
    try:
        return MemoryEmbeddingProvider(str(value))
    except ValueError as exc:
        message = "memory.embedding.provider must be 'fake'"
        raise ConfigError(message) from exc


def _validate_embedding_config(config: RuntimeMemoryEmbeddingConfig) -> None:
    if config.dimension <= 0 or config.batch_size <= 0:
        msg = "memory.embedding.dimension and batch_size must be greater than zero"
        raise ConfigError(msg)


def _validate_retrieval_config(config: RuntimeMemoryRetrievalConfig) -> None:
    positive_values = (
        config.fts_limit,
        config.vector_limit,
        config.candidate_limit,
        config.reranker_limit,
    )
    if any(value < 0 for value in positive_values):
        msg = "memory.retrieval limits must be greater than or equal to zero"
        raise ConfigError(msg)
    if not 0.0 <= config.duplicate_similarity_threshold <= 1.0:
        msg = "memory.retrieval.duplicate_similarity_threshold must be between 0.0 and 1.0"
        raise ConfigError(msg)
