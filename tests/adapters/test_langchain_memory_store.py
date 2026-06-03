from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from inspect import signature

import pytest

from iris.adapters.memory import langchain
from iris.adapters.memory.langchain import (
    LangChainMemoryStore,
    LangChainMemoryStoreError,
    LangChainMemoryStoreUnavailable,
)
from iris.contracts.memory import MemoryId, MemoryQuery, MemoryRecord, MemorySearchResult
from iris.core.ids import UserId


@dataclass(frozen=True)
class StubDocument:
    page_content: str
    metadata: Mapping[str, object]


class StubVectorStore:
    def __init__(self) -> None:
        self.documents: list[StubDocument] = []

    def add_documents(self, documents: Sequence[StubDocument]) -> None:
        self.documents.extend(documents)

    def similarity_search_with_score(
        self,
        query: str,
        *,
        k: int,
    ) -> Sequence[tuple[StubDocument, float]]:
        matches = [
            (document, 1.0) for document in self.documents if query.casefold() in document.page_content.casefold()
        ]
        return tuple(matches[:k])


def make_document(*, page_content: str, metadata: Mapping[str, object]) -> StubDocument:
    return StubDocument(page_content=page_content, metadata=metadata)


def test_langchain_memory_store_uses_iris_contracts_only() -> None:
    store = LangChainMemoryStore(StubVectorStore(), document_factory=make_document)

    put_signature = signature(store.put)
    search_signature = signature(store.search)

    assert put_signature.parameters["record"].annotation == "MemoryRecord"
    assert put_signature.return_annotation == "None"
    assert search_signature.parameters["query"].annotation == "MemoryQuery"
    assert search_signature.return_annotation != StubDocument


def test_langchain_memory_store_puts_and_searches_iris_records() -> None:
    vector_store = StubVectorStore()
    store = LangChainMemoryStore(vector_store, document_factory=make_document)
    user_id = UserId("user-1")

    store.put(
        MemoryRecord(
            id=MemoryId("m1"),
            text="User likes jasmine tea.",
            subject_id=user_id,
            salience=0.7,
        )
    )

    results = store.search(MemoryQuery(text="jasmine", subject_id=user_id))

    assert results == (
        MemorySearchResult(
            record=MemoryRecord(
                id=MemoryId("m1"),
                text="User likes jasmine tea.",
                subject_id=user_id,
                salience=0.7,
            ),
            score=1.0,
        ),
    )


def test_langchain_memory_store_filters_subject_id_after_vector_search() -> None:
    vector_store = StubVectorStore()
    store = LangChainMemoryStore(vector_store, document_factory=make_document)
    store.put(
        MemoryRecord(
            id=MemoryId("m1"),
            text="User likes tea.",
            subject_id=UserId("user-1"),
        )
    )
    store.put(
        MemoryRecord(
            id=MemoryId("m2"),
            text="User likes tea.",
            subject_id=UserId("user-2"),
        )
    )

    results = store.search(MemoryQuery(text="tea", subject_id=UserId("user-2")))

    assert [result.record.id for result in results] == [MemoryId("m2")]


def test_langchain_memory_store_reports_missing_optional_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_document_factory() -> langchain._DocumentFactory:
        raise LangChainMemoryStoreUnavailable("langchain-core is not installed")

    monkeypatch.setattr(langchain, "_load_document_factory", missing_document_factory)

    with pytest.raises(LangChainMemoryStoreUnavailable, match="langchain-core"):
        LangChainMemoryStore(StubVectorStore())


def test_langchain_memory_store_rejects_missing_vector_store_methods() -> None:
    store = LangChainMemoryStore(object(), document_factory=make_document)

    with pytest.raises(LangChainMemoryStoreError, match="add_documents"):
        store.put(MemoryRecord(id=MemoryId("m1"), text="memory"))

    with pytest.raises(LangChainMemoryStoreError, match="similarity_search"):
        store.search(MemoryQuery(text="memory"))
