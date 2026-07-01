"""metadata-aware なインメモリ VectorMemoryIndex。"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from iris.adapters.memory.utils import cosine_similarity, vector_from_embedding
from iris.contracts.memory import (
    MemoryId,
    VectorMemoryEntry,
    VectorMemoryEntryMetadata,
    VectorMemoryIndex,
    VectorMemorySearchResult,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


class InMemoryVectorMemoryIndex(VectorMemoryIndex):
    """開発・テスト向けの process-local 派生 index。"""

    def __init__(self) -> None:
        """空の process-local index を初期化する。"""
        self._entries: dict[MemoryId, VectorMemoryEntry] = {}

    @override
    def upsert(self, entry: VectorMemoryEntry) -> None:
        """Entry を検証して登録または更新する。

        Raises:
            ValueError: vector 次元と metadata が一致しない場合。
        """
        vector = vector_from_embedding(entry.vector)
        if len(vector) != entry.embedding_dimension:
            msg = "Vector dimension does not match entry metadata"
            raise ValueError(msg)
        self._entries[entry.memory_id] = entry.model_copy(update={"vector": vector})

    @override
    def delete(self, memory_id: MemoryId) -> None:
        """指定 ID の entry を削除する。"""
        self._entries.pop(memory_id, None)

    @override
    def search(
        self,
        query_vector: Sequence[float],
        *,
        limit: int,
    ) -> Sequence[VectorMemorySearchResult]:
        """Cosine similarity 降順の結果を返す。

        Returns:
            類似度降順の結果。
        """
        if limit <= 0 or not self._entries:
            return ()
        query = vector_from_embedding(query_vector)
        ranked: list[tuple[float, int, VectorMemorySearchResult]] = []
        for index, (memory_id, entry) in enumerate(self._entries.items()):
            score = cosine_similarity(query, entry.vector)
            ranked.append(
                (score, index, VectorMemorySearchResult(memory_id=memory_id, score=score))
            )
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return tuple(result for _, _, result in ranked[:limit])

    @override
    def metadata(self, memory_id: MemoryId) -> VectorMemoryEntryMetadata | None:
        """鮮度・互換性 metadata を返す。

        Returns:
            Entry metadata。未登録時は None。
        """
        entry = self._entries.get(memory_id)
        if entry is None:
            return None
        return VectorMemoryEntryMetadata(
            memory_id=entry.memory_id,
            source_digest=entry.source_digest,
            embedding_model=entry.embedding_model,
            embedding_dimension=entry.embedding_dimension,
        )

    @override
    def ids(self) -> Sequence[MemoryId]:
        """登録順の memory id を返す。

        Returns:
            登録済み memory id。
        """
        return tuple(self._entries)
