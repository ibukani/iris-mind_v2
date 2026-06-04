"""LangChainベクターストアメモリアダプタ。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast, override

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

from iris.adapters.memory.ports import MemoryStore
from iris.contracts.memory import MemoryId, MemoryQuery, MemoryRecord, MemorySearchResult
from iris.core.ids import UserId

_MEMORY_ID_KEY = "iris_memory_id"
_SUBJECT_ID_KEY = "iris_subject_id"
_SALIENCE_KEY = "iris_salience"

_ERR_REQUIRES_DOCUMENTS = (
    "LangChainMemoryStore requires a vector store with add_documents() or add_texts()."
)
_ERR_REQUIRES_SEARCH = (
    "LangChainMemoryStore requires a vector store with similarity_search_with_score() "
    "or similarity_search()."
)
_ERR_REQUIRES_LANGCHAIN_CORE = (
    "LangChainMemoryStore requires langchain-core. Install the optional LangChain "
    "dependencies or pass a document_factory explicitly."
)


class LangChainMemoryStoreError(RuntimeError):
    """オプションのLangChainメモリアダプタのベースエラー。"""


class LangChainMemoryStoreUnavailableError(LangChainMemoryStoreError):
    """このアダプタにLangChainが必要だが利用不可の場合に送出される。"""


class _DocumentLike(Protocol):
    page_content: str
    metadata: Mapping[str, object]


class DocumentFactory(Protocol):
    """LangChain互換ドキュメントを生成する呼び出し可能オブジェクトのプロトコル。"""

    def __call__(
        self,
        *,
        page_content: str,
        metadata: Mapping[str, object],
    ) -> _DocumentLike:
        """指定されたページ内容とメタデータでドキュメントを生成する。"""
        ...


class _AddDocumentsStore(Protocol):
    def add_documents(self, documents: Sequence[_DocumentLike]) -> object: ...


class _AddTextsStore(Protocol):
    def add_texts(
        self,
        texts: Sequence[str],
        metadatas: Sequence[Mapping[str, object]],
        ids: Sequence[str],
    ) -> object: ...


class _SimilaritySearchWithScoreStore(Protocol):
    def similarity_search_with_score(
        self,
        query: str,
        *,
        k: int,
    ) -> Sequence[tuple[_DocumentLike, float]]: ...


class _SimilaritySearchStore(Protocol):
    def similarity_search(self, query: str, *, k: int) -> Sequence[_DocumentLike]: ...


class LangChainMemoryStore(MemoryStore):
    """LangChainベクターストア形式オブジェクトのMemoryStoreアダプタ。"""

    def __init__(
        self,
        vector_store: object,
        *,
        document_factory: DocumentFactory | None = None,
    ) -> None:
        """LangChainベクターストアとカスタムドキュメントファクトリで初期化する。

        Args:
            vector_store: A LangChain-compatible vector store object.
            document_factory: Optional factory for creating documents. Defaults to
                langchain_core.documents.Document.
        """
        self._vector_store = vector_store
        self._document_factory = document_factory or _load_document_factory()

    @override
    def put(self, record: MemoryRecord) -> None:
        """メモリレコードをベクターストアに保存する。

        Raises:
            LangChainMemoryStoreError: add_documents/add_texts 非サポート時。
        """
        metadata = _metadata_from_record(record)
        if hasattr(self._vector_store, "add_documents"):
            document = self._document_factory(page_content=record.text, metadata=metadata)
            cast("_AddDocumentsStore", self._vector_store).add_documents((document,))
            return

        if hasattr(self._vector_store, "add_texts"):
            cast("_AddTextsStore", self._vector_store).add_texts(
                (record.text,),
                (metadata,),
                (str(record.id),),
            )
            return

        raise LangChainMemoryStoreError(_ERR_REQUIRES_DOCUMENTS)

    @override
    def search(self, query: MemoryQuery) -> Sequence[MemorySearchResult]:
        """クエリに一致するレコードをベクターストアから検索する。

        Returns:
            Sequence[MemorySearchResult]: クエリに一致するメモリレコードのシーケンス。

        Raises:
            LangChainMemoryStoreError: similarity_search_with_score 非サポート時。
        """
        if query.limit <= 0:
            return ()

        if hasattr(self._vector_store, "similarity_search_with_score"):
            raw_results = cast(
                "_SimilaritySearchWithScoreStore",
                self._vector_store,
            ).similarity_search_with_score(query.text, k=query.limit)
            results = tuple(
                MemorySearchResult(record=_record_from_document(document), score=float(score))
                for document, score in raw_results
            )
        elif hasattr(self._vector_store, "similarity_search"):
            documents = cast("_SimilaritySearchStore", self._vector_store).similarity_search(
                query.text,
                k=query.limit,
            )
            results = tuple(
                MemorySearchResult(record=_record_from_document(document), score=1.0)
                for document in documents
            )
        else:
            raise LangChainMemoryStoreError(_ERR_REQUIRES_SEARCH)

        return tuple(
            result
            for result in results
            if query.subject_id is None or result.record.subject_id == query.subject_id
        )[: query.limit]


def _load_document_factory() -> DocumentFactory:
    try:
        from langchain_core.documents import (  # noqa: PLC0415  # conditional optional dependency
            Document,
        )
    except ImportError as exc:  # pragma: no cover - covered with monkeypatched loader
        raise LangChainMemoryStoreUnavailableError(_ERR_REQUIRES_LANGCHAIN_CORE) from exc

    return cast("DocumentFactory", Document)


def _metadata_from_record(record: MemoryRecord) -> Mapping[str, object]:
    metadata: dict[str, object] = {
        _MEMORY_ID_KEY: str(record.id),
        _SALIENCE_KEY: record.salience,
    }
    if record.subject_id is not None:
        metadata[_SUBJECT_ID_KEY] = str(record.subject_id)
    return metadata


def _record_from_document(document: _DocumentLike) -> MemoryRecord:
    memory_id = _metadata_text(document.metadata, _MEMORY_ID_KEY)
    if memory_id is None:
        err_msg = f"LangChain document metadata must include '{_MEMORY_ID_KEY}'."
        raise LangChainMemoryStoreError(err_msg)

    subject_id = _metadata_text(document.metadata, _SUBJECT_ID_KEY)
    salience = _metadata_float(document.metadata, _SALIENCE_KEY)
    return MemoryRecord(
        id=MemoryId(memory_id),
        text=document.page_content,
        subject_id=UserId(subject_id) if subject_id is not None else None,
        salience=salience,
    )


def _metadata_text(metadata: Mapping[str, object], key: str) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    return str(value)


def _metadata_float(metadata: Mapping[str, object], key: str) -> float:
    value = metadata.get(key)
    if value is None:
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    return float(str(value))
