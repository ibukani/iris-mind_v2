"""metadata-aware なインメモリ VectorMemoryIndex。"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from iris.adapters.memory.utils import cosine_similarity, vector_from_embedding
from iris.contracts.memory import (
    MemoryId,
    VectorMemoryEntry,
    VectorMemoryEntryMetadata,
    VectorMemoryIndex,
    VectorMemoryIndexError,
    VectorMemorySearchFilter,
    VectorMemorySearchResult,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


def _matches_filter(entry: VectorMemoryEntry, filters: VectorMemorySearchFilter | None) -> bool:
    """Entry が検索前フィルタを満たすか判定する。

    Returns:
        フィルタ条件を満たす場合 True。
    """
    if filters is None:
        return True
    return (
        (filters.include_archived or not entry.archived)
        and (filters.actor_id is None or entry.actor_id == filters.actor_id)
        and (filters.space_id is None or entry.space_id == filters.space_id)
        and (filters.kind is None or entry.kind == filters.kind)
    )


class InMemoryVectorMemoryIndex(VectorMemoryIndex):
    """開発・テスト向けの process-local 派生 index。"""

    def __init__(self) -> None:
        """空の process-local index を初期化する。"""
        self._entries: dict[MemoryId, VectorMemoryEntry] = {}

    @override
    def upsert(self, entry: VectorMemoryEntry) -> None:
        """Entry を検証して登録または更新する。

        Raises:
            VectorMemoryIndexError: vector 次元と metadata が一致しない場合。
        """
        try:
            vector = vector_from_embedding(entry.vector)
        except ValueError as exc:
            msg = "Vector entry contains an invalid embedding"
            raise VectorMemoryIndexError(msg) from exc
        if len(vector) != entry.embedding_dimension:
            msg = "Vector dimension does not match entry metadata"
            raise VectorMemoryIndexError(msg)
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
        filters: VectorMemorySearchFilter | None = None,
    ) -> Sequence[VectorMemorySearchResult]:
        """Cosine similarity 降順の結果を返す。

        Returns:
            類似度降順の結果。

        Raises:
            VectorMemoryIndexError: query vector が不正または登録 entry と次元不一致の場合。
        """
        if limit <= 0 or not self._entries:
            return ()
        try:
            query = vector_from_embedding(query_vector)
        except ValueError as exc:
            msg = "Vector query contains an invalid embedding"
            raise VectorMemoryIndexError(msg) from exc
        ranked: list[tuple[float, int, VectorMemorySearchResult]] = []
        for index, (memory_id, entry) in enumerate(self._entries.items()):
            if not _matches_filter(entry, filters):
                continue
            try:
                score = cosine_similarity(query, entry.vector)
            except ValueError as exc:
                msg = "Vector query dimension does not match entry"
                raise VectorMemoryIndexError(msg) from exc
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
            embedding_provider=entry.embedding_provider,
            embedding_model=entry.embedding_model,
            embedding_dimension=entry.embedding_dimension,
            actor_id=entry.actor_id,
            space_id=entry.space_id,
            kind=entry.kind,
            archived=entry.archived,
            source_observation_id=entry.source_observation_id,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )

    @override
    def ids(self) -> Sequence[MemoryId]:
        """登録順の memory id を返す。

        Returns:
            登録済み memory id。
        """
        return tuple(self._entries)
