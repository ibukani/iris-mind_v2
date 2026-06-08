"""インメモリ VectorMemoryIndex の実装。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import override

from iris.adapters.memory.utils import cosine_similarity, vector_from_embedding
from iris.contracts.memory import MemoryId, VectorMemoryIndex, VectorMemorySearchResult

EmbeddingFunction = Callable[[str], Sequence[float]]


class InMemoryVectorMemoryIndex(VectorMemoryIndex):
    """アダプタテストとローカル配線のための決定論的インメモリ VectorMemoryIndex。"""

    def __init__(self, embed_text: EmbeddingFunction) -> None:
        """埋め込み関数で初期化する。

        Args:
            embed_text: テキストを float ベクトルに変換する関数。
        """
        self._embed_text = embed_text
        self._entries: dict[MemoryId, tuple[tuple[float, ...], str]] = {}

    @override
    def upsert(
        self,
        memory_id: MemoryId,
        text: str,
        metadata: Mapping[str, str],
    ) -> None:
        """メモリテキストとメタデータをインデックスに登録または更新する。"""
        _ = metadata
        vector = vector_from_embedding(self._embed_text(text))
        self._entries[memory_id] = (vector, text)

    @override
    def delete(self, memory_id: MemoryId) -> None:
        """指定 ID のエントリをインデックスから削除する。"""
        self._entries.pop(memory_id, None)

    @override
    def search(self, query: str, *, limit: int) -> Sequence[VectorMemorySearchResult]:
        """クエリテキストに対するベクトル類似度検索を実行する。

        Args:
            query: 検索クエリテキスト。
            limit: 返す結果の最大件数。

        Returns:
            Sequence[VectorMemorySearchResult]: 類似度スコア降順の結果。
        """
        if limit <= 0 or not self._entries:
            return ()

        query_vector = vector_from_embedding(self._embed_text(query))
        ranked: list[tuple[float, int, VectorMemorySearchResult]] = []
        for index, (memory_id, (vector, _text)) in enumerate(self._entries.items()):
            score = cosine_similarity(query_vector, vector)
            result = VectorMemorySearchResult(memory_id=memory_id, score=score)
            ranked.append((score, index, result))

        ranked.sort(key=lambda item: (-item[0], item[1]))
        return tuple(result for _, _, result in ranked[:limit])
