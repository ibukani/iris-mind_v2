"""インメモリおよび LangChain バックエンドのメモリストア用ワイヤリング関数。"""

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
