from __future__ import annotations

from collections.abc import Sequence

from iris.adapters.memory.langchain import LangChainMemoryStore
from iris.adapters.memory.ports import MemoryStore
from iris.adapters.memory.vector import EmbeddingFunction, InMemoryVectorMemoryStore
from iris.contracts.memory import MemoryRecord


def wire_in_memory_vector_store(
    embed_text: EmbeddingFunction,
    records: Sequence[MemoryRecord] = (),
) -> MemoryStore:
    return InMemoryVectorMemoryStore(embed_text=embed_text, records=records)


def wire_langchain_memory_store(
    vector_store: object,
) -> MemoryStore:
    return LangChainMemoryStore(vector_store)
