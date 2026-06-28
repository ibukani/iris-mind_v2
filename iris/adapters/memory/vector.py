"""インメモリベクター型MemoryStore実装。"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import override

from iris.contracts.memory import MemoryStore
from iris.adapters.memory.utils import cosine_similarity, vector_from_embedding
from iris.contracts.memory import MemoryId, MemoryQuery, MemoryRecord, MemorySearchResult

EmbeddingFunction = Callable[[str], Sequence[float]]


class InMemoryVectorMemoryStore(MemoryStore):
    """アダプタテストとローカル配線のための決定論的インメモリベクターMemoryStore。"""

    def __init__(
        self,
        embed_text: EmbeddingFunction,
        records: Sequence[MemoryRecord] = (),
    ) -> None:
        """埋め込み関数とオプションのシードレコードで初期化する。

        Args:
            embed_text: Function that converts text to a vector of floats.
            records: Initial memory records to populate the store.
        """
        self._embed_text = embed_text
        self._entries: list[tuple[MemoryRecord, tuple[float, ...]]] = []
        for record in records:
            self.put(record)

    @override
    def get(self, memory_id: MemoryId) -> MemoryRecord | None:
        """指定 ID のメモリレコードを返す。

        Args:
            memory_id: 検索するメモリ ID。

        Returns:
            MemoryRecord | None: 一致したレコード。存在しない場合は None。
        """
        for record, _vector in self._entries:
            if record.id == memory_id:
                return record
        return None

    @override
    def put(self, record: MemoryRecord) -> None:
        """メモリレコードを埋め込みベクターとともに保存する。"""
        self._entries.append((record, vector_from_embedding(self._embed_text(record.text))))

    @override
    def search(self, query: MemoryQuery) -> Sequence[MemorySearchResult]:
        """クエリ埋め込みに対するコサイン類似度でメモリレコードを検索する。

        Returns:
            Sequence[MemorySearchResult]: コサイン類似度順のメモリレコード。
        """
        if query.limit <= 0:
            return ()

        query_vector = vector_from_embedding(self._embed_text(query.text))
        ranked: list[tuple[float, int, MemorySearchResult]] = []
        for index, (record, record_vector) in enumerate(self._entries):
            if query.actor_id is not None and record.actor_id != query.actor_id:
                continue
            if query.space_id is not None and record.space_id != query.space_id:
                continue
            score = cosine_similarity(query_vector, record_vector)
            ranked.append((score, index, MemorySearchResult(record=record, score=score)))

        ranked.sort(key=lambda item: (-item[0], item[1]))
        return tuple(result for _, _, result in ranked[: query.limit])
