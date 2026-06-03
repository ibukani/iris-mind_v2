"""Memory store wiring functions for in-memory and LangChain backends."""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.adapters.memory.langchain import LangChainMemoryStore
from iris.adapters.memory.vector import EmbeddingFunction, InMemoryVectorMemoryStore

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.adapters.memory.ports import MemoryStore
    from iris.contracts.memory import MemoryRecord


def wire_in_memory_vector_store(
    embed_text: EmbeddingFunction,
    records: Sequence[MemoryRecord] = (),
) -> MemoryStore:
    """Wire an in-memory vector memory store.

    Args:
        embed_text: Embedding function for text vectors.
        records: Initial memory records to seed the store.

    Returns:
        An InMemoryVectorMemoryStore instance.
    """
    return InMemoryVectorMemoryStore(embed_text=embed_text, records=records)


def wire_langchain_memory_store(
    vector_store: object,
) -> MemoryStore:
    """Wire a LangChain-backed memory store.

    Args:
        vector_store: A LangChain vector store instance.

    Returns:
        A LangChainMemoryStore instance.
    """
    return LangChainMemoryStore(vector_store)
