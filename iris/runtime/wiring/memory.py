"""インメモリおよび LangChain バックエンドのメモリストア用ワイヤリング関数。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.adapters.memory.langchain import LangChainMemoryStore
from iris.adapters.memory.vector import InMemoryVectorMemoryStore
from iris.adapters.memory.vector_index import InMemoryVectorMemoryIndex
from iris.cognitive.memory.hybrid import HybridMemoryRetriever

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.adapters.memory.ports import MemoryStore
    from iris.adapters.memory.sqlite import SQLiteMemoryStore
    from iris.adapters.memory.vector import EmbeddingFunction
    from iris.cognitive.memory.retrieval import MemoryRetriever
    from iris.contracts.memory import (
        MemoryQuery,
        MemoryRecord,
        MemorySearchResult,
        VectorMemoryIndex,
    )


def wire_in_memory_vector_store(
    embed_text: EmbeddingFunction,
    records: Sequence[MemoryRecord] = (),
) -> MemoryStore:
    """インメモリのベクトルメモリストアを組み立てる。

    Args:
        embed_text: テキストベクトル用の埋め込み関数。
        records: ストアに投入する初期メモリレコード。

    Returns:
        InMemoryVectorMemoryStore インスタンス。
    """
    return InMemoryVectorMemoryStore(embed_text=embed_text, records=records)


def wire_langchain_memory_store(
    vector_store: object,
) -> MemoryStore:
    """LangChain バックエンドのメモリストアを組み立てる。

    Args:
        vector_store: LangChain のベクトルストアインスタンス。

    Returns:
        LangChainMemoryStore インスタンス。
    """
    return LangChainMemoryStore(vector_store)


class SQLiteFTS5MemoryRetriever:
    """SQLiteMemoryStore.search_fts5 を MemoryRetriever Protocol としてラップする。"""

    def __init__(self, store: SQLiteMemoryStore) -> None:
        """SQLiteMemoryStore で初期化する。

        Args:
            store: FTS5 検索を提供する SQLiteMemoryStore。
        """
        self._store = store

    def search(self, query: MemoryQuery) -> Sequence[MemorySearchResult]:
        """FTS5 全文検索を実行する。

        Args:
            query: 検索クエリ。

        Returns:
            Sequence[MemorySearchResult]: FTS5 検索結果。
        """
        return self._store.search_fts5(query)


def wire_hybrid_memory_retriever(
    *,
    fts_retriever: MemoryRetriever,
    vector_index: VectorMemoryIndex,
    store: MemoryStore,
    fts_limit: int = 10,
    vector_limit: int = 10,
) -> HybridMemoryRetriever:
    """FTS5 とベクトル検索を統合したハイブリッドレトリーバーを組み立てる。

    Args:
        fts_retriever: FTS5 全文検索バックエンド。
        vector_index: ベクトル類似度検索インデックス。
        store: ベクトル検索結果の memory_id → MemoryRecord 解決用ストア。
        fts_limit: FTS5 検索の取得上限。
        vector_limit: ベクトル検索の取得上限。

    Returns:
        HybridMemoryRetriever インスタンス。
    """
    return HybridMemoryRetriever(
        fts_retriever=fts_retriever,
        vector_index=vector_index,
        store=store,
        fts_limit=fts_limit,
        vector_limit=vector_limit,
    )


def wire_sqlite_hybrid_memory_retriever(
    store: SQLiteMemoryStore,
    embed_text: EmbeddingFunction,
    *,
    fts_limit: int = 10,
    vector_limit: int = 10,
) -> tuple[HybridMemoryRetriever, InMemoryVectorMemoryIndex]:
    """SQLiteMemoryStore とベクトルインデックスからハイブリッドレトリーバーを組み立てる。

    Args:
        store: SQLiteMemoryStore（FTS5 全文検索 + レコード解決用）。
        embed_text: テキストベクトル用の埋め込み関数。
        fts_limit: FTS5 検索の取得上限。
        vector_limit: ベクトル検索の取得上限。

    Returns:
        tuple[HybridMemoryRetriever, InMemoryVectorMemoryIndex]:
            ハイブリッドレトリーバーとベクトルインデックスのタプル。
    """
    fts = SQLiteFTS5MemoryRetriever(store)
    vector = InMemoryVectorMemoryIndex(embed_text)
    hybrid = wire_hybrid_memory_retriever(
        fts_retriever=fts,
        vector_index=vector,
        store=store,
        fts_limit=fts_limit,
        vector_limit=vector_limit,
    )
    return hybrid, vector
