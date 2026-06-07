"""インメモリ VectorMemoryIndex の実装。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from math import isclose, sqrt
from typing import override

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
        vector = _vector_from_embedding(self._embed_text(text))
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

        query_vector = _vector_from_embedding(self._embed_text(query))
        ranked: list[tuple[float, int, VectorMemorySearchResult]] = []
        for index, (memory_id, (vector, _text)) in enumerate(self._entries.items()):
            score = _cosine_similarity(query_vector, vector)
            result = VectorMemorySearchResult(memory_id=memory_id, score=score)
            ranked.append((score, index, result))

        ranked.sort(key=lambda item: (-item[0], item[1]))
        return tuple(result for _, _, result in ranked[:limit])


_ERR_EMPTY_EMBEDDING = "Embedding function must return at least one dimension."
_ERR_DIMENSION_MISMATCH = "Embedding function must return vectors with stable dimensions."


def _vector_from_embedding(values: Sequence[float]) -> tuple[float, ...]:
    vector = tuple(float(value) for value in values)
    if not vector:
        raise ValueError(_ERR_EMPTY_EMBEDDING)
    return vector


def _cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise ValueError(_ERR_DIMENSION_MISMATCH)

    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if isclose(left_norm, 0.0) or isclose(right_norm, 0.0):
        return 0.0

    dot_product = sum(
        left_value * right_value for left_value, right_value in zip(left, right, strict=True)
    )
    return dot_product / (left_norm * right_norm)
