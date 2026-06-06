# Copyright 2025 Iris Mind
"""Tests for memory wiring functions producing concrete store instances."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from iris.adapters.memory import langchain
from iris.adapters.memory.langchain import LangChainMemoryStore
from iris.adapters.memory.vector import InMemoryVectorMemoryStore
from iris.contracts.memory import MemoryId, MemoryQuery, MemoryRecord
from iris.runtime.wiring.memory import wire_in_memory_vector_store, wire_langchain_memory_store

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    import pytest


@dataclass(frozen=True)
class StubDocument:
    """Stub document for testing LangChain document factory wiring."""

    page_content: str
    metadata: Mapping[str, object]


class StubVectorStore:
    """Stub vector store for testing memory wiring functions."""

    def similarity_search(self, _query: str, *, _k: int) -> Sequence[StubDocument]:
        """Return empty results."""
        _ = self, _query, _k
        return ()

    def add_documents(self, _documents: Sequence[object]) -> None:
        """No-op add documents."""


def embed_text(text: str) -> tuple[float]:
    """Return a 1d embedding based on whether text is non-empty."""
    return (1.0 if text else 0.0,)


def make_document(*, page_content: str, metadata: Mapping[str, object]) -> StubDocument:
    """Return a StubDocument with the given content and metadata."""
    return StubDocument(page_content=page_content, metadata=metadata)


def test_wire_in_memory_vector_store_returns_memory_store() -> None:
    """Verify wire_in_memory_vector_store returns a populated InMemoryVectorMemoryStore."""
    store = wire_in_memory_vector_store(
        embed_text,
        records=(MemoryRecord(id=MemoryId("m1"), text="memory"),),
    )

    assert isinstance(store, InMemoryVectorMemoryStore)
    assert store.search(MemoryQuery(text="memory"))[0].record.id == MemoryId("m1")


def test_wire_langchain_memory_store_is_explicit_adapter_wiring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify wire_langchain_memory_store returns a LangChainMemoryStore instance."""

    def load_document_factory() -> langchain.DocumentFactory:
        return cast("langchain.DocumentFactory", make_document)

    monkeypatch.setattr(langchain, "_load_document_factory", load_document_factory)

    store = wire_langchain_memory_store(StubVectorStore())

    assert isinstance(store, LangChainMemoryStore)
