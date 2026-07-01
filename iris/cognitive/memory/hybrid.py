"""ハイブリッドメモリ検索: FTS5 + ベクトル統合と再ランク付け。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from iris.cognitive.memory.retrieval import MemoryRetriever
from iris.contracts.memory import (
    MemoryQuery,
    MemorySearchResult,
    VectorMemorySearchFilter,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.contracts.embeddings import EmbeddingModel
    from iris.contracts.memory import (
        MemoryId,
        MemoryStore,
        VectorMemoryIndex,
        VectorMemorySearchResult,
    )


_ERR_WEIGHT_TOTAL = "Total reranker weight must be > 0"


@dataclass(frozen=True)
class _HybridScore:
    """ハイブリッド検索結果のスコア保持用データクラス。"""

    fts_score: float
    vector_score: float
    result: MemorySearchResult


class MemoryReranker:
    """FTS5 とベクトル検索結果を統合スコアで再ランク付けする。"""

    def __init__(
        self,
        *,
        fts_weight: float = 0.35,
        vector_weight: float = 0.35,
        salience_weight: float = 0.15,
        confidence_weight: float = 0.15,
    ) -> None:
        """重み係数で初期化する。

        Args:
            fts_weight: FTS5 スコアの重み。
            vector_weight: ベクトル類似度スコアの重み。
            salience_weight: メモリ salience の重み。
            confidence_weight: メモリ confidence の重み。

        Raises:
            ValueError: 全重みの合計が 0 以下の場合。
        """
        total = fts_weight + vector_weight + salience_weight + confidence_weight
        if total <= 0:
            raise ValueError(_ERR_WEIGHT_TOTAL)
        self._fts_weight = fts_weight / total
        self._vector_weight = vector_weight / total
        self._salience_weight = salience_weight / total
        self._confidence_weight = confidence_weight / total

    def rerank(
        self,
        fts_results: Sequence[MemorySearchResult],
        vector_results: Sequence[MemorySearchResult],
        *,
        limit: int = 5,
    ) -> Sequence[MemorySearchResult]:
        """FTS5 とベクトル結果を統合して再ランク付けする。

        Args:
            fts_results: FTS5 検索結果。
            vector_results: ベクトル検索結果。
            limit: 返す結果の最大件数。

        Returns:
            Sequence[MemorySearchResult]: 統合スコア降順の結果。
        """
        if limit <= 0:
            return ()

        merged = self._merge_results(fts_results, vector_results)
        if not merged:
            return ()

        return self._rank_merged(merged, limit=limit)

    @staticmethod
    def _merge_results(
        fts_results: Sequence[MemorySearchResult],
        vector_results: Sequence[MemorySearchResult],
    ) -> dict[MemoryId, _HybridScore]:
        """FTS5 とベクトル結果を memory_id 単位でマージする。

        Returns:
            dict[MemoryId, _HybridScore]: memory_id ごとのスコアマップ。
        """
        merged: dict[MemoryId, _HybridScore] = {}
        for result in fts_results:
            merged[result.record.id] = _HybridScore(
                fts_score=result.score,
                vector_score=0.0,
                result=result,
            )
        for result in vector_results:
            key = result.record.id
            if key in merged:
                existing_score = merged[key]
                merged[key] = _HybridScore(
                    fts_score=existing_score.fts_score,
                    vector_score=result.score,
                    result=existing_score.result,
                )
            else:
                merged[key] = _HybridScore(
                    fts_score=0.0,
                    vector_score=result.score,
                    result=result,
                )
        return merged

    def _rank_merged(
        self,
        merged: dict[MemoryId, _HybridScore],
        *,
        limit: int,
    ) -> Sequence[MemorySearchResult]:
        """マージ済み結果を composite score でランク付けする。

        Returns:
            Sequence[MemorySearchResult]: 統合スコア降順の結果。
        """
        fts_max = float("-inf")
        vec_max = float("-inf")
        for score_entry in merged.values():
            fts_max = max(fts_max, score_entry.fts_score)
            vec_max = max(vec_max, score_entry.vector_score)
        if fts_max == 0:
            fts_max = 1.0
        if vec_max == 0:
            vec_max = 1.0

        ranked: list[tuple[float, int, MemorySearchResult]] = []
        for index, score_entry in enumerate(merged.values()):
            normalized_fts = score_entry.fts_score / fts_max
            normalized_vec = score_entry.vector_score / vec_max
            composite = (
                normalized_fts * self._fts_weight
                + normalized_vec * self._vector_weight
                + score_entry.result.record.salience * self._salience_weight
                + score_entry.result.record.confidence * self._confidence_weight
            )
            entry = MemorySearchResult(record=score_entry.result.record, score=composite)
            ranked.append((composite, index, entry))

        def _sort_key(item: tuple[float, int, MemorySearchResult]) -> tuple[float, int]:
            return (-item[0], item[1])

        ranked.sort(key=_sort_key)
        return tuple(result for _, _, result in ranked[:limit])


class HybridMemoryRetriever(MemoryRetriever):
    """FTS5 全文検索とベクトル類似度検索を統合するハイブリッドレトリーバー。

    MemoryRetriever Protocol を実装する。
    """

    def __init__(
        self,
        *,
        fts_retriever: MemoryRetriever,
        vector_index: VectorMemoryIndex,
        embedding: EmbeddingModel,
        store: MemoryStore,
        fts_limit: int = 10,
        vector_limit: int = 10,
    ) -> None:
        """FTS5 レトリーバー、ベクトルインデックス、ストアで初期化する。

        Args:
            fts_retriever: FTS5 全文検索バックエンド。
            vector_index: ベクトル類似度検索インデックス。
            embedding: query embedding model。
            store: ベクトル検索結果の memory_id → MemoryRecord 解決用ストア。
            fts_limit: FTS5 検索の取得上限。
            vector_limit: ベクトル検索の取得上限。
        """
        self._fts = fts_retriever
        self._vector = vector_index
        self._embedding = embedding
        self._store = store
        self._reranker = MemoryReranker()
        self._fts_limit = fts_limit
        self._vector_limit = vector_limit

    @override
    def search(self, query: MemoryQuery) -> Sequence[MemorySearchResult]:
        """FTS5 とベクトルを統合して検索する。

        Args:
            query: 検索クエリ。

        Returns:
            Sequence[MemorySearchResult]: 統合スコア降順の検索結果。
        """
        if query.limit <= 0:
            return ()

        fts_query = MemoryQuery(
            text=query.text,
            actor_id=query.actor_id,
            space_id=query.space_id,
            limit=self._fts_limit,
            kind=query.kind,
            include_archived=query.include_archived,
        )
        fts_results = tuple(self._fts.search(fts_query))

        vector_raw = self._vector.search(
            self._embedding.embed(query.text),
            limit=self._vector_limit,
            filters=VectorMemorySearchFilter(
                actor_id=query.actor_id,
                space_id=query.space_id,
                kind=query.kind,
                include_archived=query.include_archived,
            ),
        )
        vector_results = self._resolve_vector_results(vector_raw, query)

        return self._reranker.rerank(
            fts_results,
            vector_results,
            limit=query.limit,
        )

    def _resolve_vector_results(
        self,
        raw: Sequence[VectorMemorySearchResult],
        query: MemoryQuery,
    ) -> Sequence[MemorySearchResult]:
        """ベクトル検索結果を MemoryRecord で解決する。

        Args:
            raw: VectorMemoryIndex.search の結果。
            query: 元の検索クエリ（フィルタ用）。

        Returns:
            Sequence[MemorySearchResult]: 解決済みベクトル検索結果。
        """
        results: list[MemorySearchResult] = []
        for item in raw:
            record = self._store.get(item.memory_id)
            if record is None:
                continue
            if not query.include_archived and record.archived:
                continue
            if query.actor_id is not None and record.actor_id != query.actor_id:
                continue
            if query.space_id is not None and record.space_id != query.space_id:
                continue
            if query.kind is not None and record.kind != query.kind:
                continue
            results.append(MemorySearchResult(record=record, score=item.score))
        return tuple(results)
