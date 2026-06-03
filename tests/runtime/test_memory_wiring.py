from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pytest

from iris.adapters.memory import langchain
from iris.adapters.memory.langchain import LangChainMemoryStore
from iris.adapters.memory.vector import InMemoryVectorMemoryStore
from iris.contracts.memory import MemoryId, MemoryQuery, MemoryRecord
from iris.runtime.wiring.memory import wire_in_memory_vector_store, wire_langchain_memory_store


@dataclass(frozen=True)
class StubDocument:
    page_content: str
    metadata: Mapping[str, object]


class StubVectorStore:
    def similarity_search(self, query: str, *, k: int) -> Sequence[StubDocument]:
        return ()

    def add_documents(self, documents: Sequence[object]) -> None:
        return None


def embed_text(text: str) -> tuple[float]:
    return (1.0 if text else 0.0,)


def make_document(*, page_content: str, metadata: Mapping[str, object]) -> StubDocument:
    return StubDocument(page_content=page_content, metadata=metadata)


def test_wire_in_memory_vector_store_returns_memory_store() -> None:
    store = wire_in_memory_vector_store(
        embed_text,
        records=(MemoryRecord(id=MemoryId("m1"), text="memory"),),
    )

    assert isinstance(store, InMemoryVectorMemoryStore)
    assert store.search(MemoryQuery(text="memory"))[0].record.id == MemoryId("m1")


def test_wire_langchain_memory_store_is_explicit_adapter_wiring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def load_document_factory() -> langchain._DocumentFactory:
        return make_document

    monkeypatch.setattr(langchain, "_load_document_factory", load_document_factory)

    store = wire_langchain_memory_store(StubVectorStore())

    assert isinstance(store, LangChainMemoryStore)
