"""Iris契約を使用したLangChainMemoryStoreアダプターのテスト。"""

from __future__ import annotations

from dataclasses import dataclass
from inspect import signature
from typing import TYPE_CHECKING, cast

import pytest

from iris.adapters.memory import langchain
from iris.adapters.memory.langchain import (
    LangChainMemoryStore,
    LangChainMemoryStoreError,
    LangChainMemoryStoreUnavailableError,
)
from iris.contracts.memory import MemoryId, MemoryQuery, MemoryRecord, MemorySearchResult
from iris.core.ids import ActorId, SpaceId

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


@dataclass(frozen=True)
class StubDocument:
    """LangChainドキュメントファクトリと互換性のあるスタブドキュメント。"""

    page_content: str
    metadata: Mapping[str, object]


class StubVectorStore:
    """LangChainMemoryStoreテスト用のスタブベクターストア。"""

    def __init__(self) -> None:
        """空のドキュメントストアを初期化する。"""
        self.documents: list[StubDocument] = []

    def add_documents(self, documents: Sequence[StubDocument]) -> None:
        """ドキュメントをスタブストアに追加する。"""
        self.documents.extend(documents)

    def similarity_search_with_score(
        self,
        query: str,
        *,
        k: int,
    ) -> Sequence[tuple[StubDocument, float]]:
        """casefoldテキスト包含によるスタブ一致結果を返す。

        Returns:
            Sequence[tuple[StubDocument, float]]: 一致ドキュメントとスコアのシーケンス。
        """
        matches = [
            (document, 1.0)
            for document in self.documents
            if query.casefold() in document.page_content.casefold()
        ]
        return tuple(matches[:k])


def make_document(*, page_content: str, metadata: Mapping[str, object]) -> StubDocument:
    """指定されたコンテンツとメタデータを持つStubDocumentを返す。

    Returns:
        StubDocument: 作成されたスタブドキュメント。
    """
    return StubDocument(page_content=page_content, metadata=metadata)


def document_factory() -> langchain.DocumentFactory:
    """LangChainMemoryStoreの引数型と互換性のあるファクトリを返す。

    Returns:
        DocumentFactory: make_documentと互換のドキュメントファクトリ。
    """
    return cast("langchain.DocumentFactory", make_document)


def test_langchain_memory_store_uses_iris_contracts_only() -> None:
    """put/searchのシグネチャがLangChain型ではなくIris契約を使用することを確認する。"""
    store = LangChainMemoryStore(StubVectorStore(), document_factory=document_factory())

    put_signature = signature(store.put)
    search_signature = signature(store.search)

    assert put_signature.parameters["record"].annotation == "MemoryRecord"
    assert put_signature.return_annotation == "None"
    assert search_signature.parameters["query"].annotation == "MemoryQuery"
    assert search_signature.return_annotation != StubDocument


def test_langchain_memory_store_puts_and_searches_iris_records() -> None:
    """Iris MemoryRecordがLangChainを通じてput/searchのラウンドトリップを行うことを確認する。"""
    vector_store = StubVectorStore()
    store = LangChainMemoryStore(vector_store, document_factory=document_factory())
    actor_id = ActorId("actor-1")

    store.put(
        MemoryRecord(
            id=MemoryId("m1"),
            text="User likes jasmine tea.",
            actor_id=actor_id,
            space_id=SpaceId("space-1"),
            salience=0.7,
        )
    )

    results = store.search(
        MemoryQuery(text="jasmine", actor_id=actor_id, space_id=SpaceId("space-1"))
    )

    assert results == (
        MemorySearchResult(
            record=MemoryRecord(
                id=MemoryId("m1"),
                text="User likes jasmine tea.",
                actor_id=actor_id,
                space_id=SpaceId("space-1"),
                salience=0.7,
            ),
            score=1.0,
        ),
    )


def test_langchain_memory_store_filters_actor_id_after_vector_search() -> None:
    """ベクトル類似度検索後にactor_idフィルタリングが適用されることを確認する。"""
    vector_store = StubVectorStore()
    store = LangChainMemoryStore(vector_store, document_factory=document_factory())
    store.put(
        MemoryRecord(
            id=MemoryId("m1"),
            text="User likes tea.",
            actor_id=ActorId("actor-1"),
        )
    )
    store.put(
        MemoryRecord(
            id=MemoryId("m2"),
            text="User likes tea.",
            actor_id=ActorId("actor-2"),
        )
    )

    results = store.search(MemoryQuery(text="tea", actor_id=ActorId("actor-2")))

    assert [result.record.id for result in results] == [MemoryId("m2")]


def test_langchain_memory_store_filters_space_id_after_vector_search() -> None:
    """ベクトル類似度検索後にspace_idフィルタリングが適用されることを確認する。"""
    vector_store = StubVectorStore()
    store = LangChainMemoryStore(vector_store, document_factory=document_factory())
    store.put(
        MemoryRecord(
            id=MemoryId("m1"),
            text="User likes tea.",
            space_id=SpaceId("space-1"),
        )
    )
    store.put(
        MemoryRecord(
            id=MemoryId("m2"),
            text="User likes tea.",
            space_id=SpaceId("space-2"),
        )
    )

    results = store.search(MemoryQuery(text="tea", space_id=SpaceId("space-2")))

    assert [result.record.id for result in results] == [MemoryId("m2")]


def test_langchain_memory_store_reports_missing_optional_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """langchain-coreが欠落している場合にLangChainMemoryStoreがUnavailableErrorを発生させることを確認する。"""

    def missing_document_factory() -> langchain.DocumentFactory:
        msg = "langchain-core is not installed"
        raise LangChainMemoryStoreUnavailableError(msg)

    monkeypatch.setattr(langchain, "_load_document_factory", missing_document_factory)

    with pytest.raises(LangChainMemoryStoreUnavailableError, match="langchain-core"):
        LangChainMemoryStore(StubVectorStore())


def test_langchain_memory_store_rejects_missing_vector_store_methods() -> None:
    """ベクターストアのメソッド欠落時にLangChainMemoryStoreがエラーを発生させることを確認する。"""
    store = LangChainMemoryStore(object(), document_factory=document_factory())

    with pytest.raises(LangChainMemoryStoreError, match="add_documents"):
        store.put(MemoryRecord(id=MemoryId("m1"), text="memory"))

    with pytest.raises(LangChainMemoryStoreError, match="similarity_search"):
        store.search(MemoryQuery(text="memory"))
