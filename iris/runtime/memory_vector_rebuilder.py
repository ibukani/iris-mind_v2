"""正本 MemoryStore から vector index を再構築する。"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from iris.contracts.memory import (
    MemoryQuery,
    MemoryRecord,
    MutableMemoryStore,
    VectorMemoryEntryMetadata,
    VectorMemoryIndex,
    memory_record_digest,
    vector_memory_entry_from_record,
)

if TYPE_CHECKING:
    from iris.contracts.embeddings import EmbeddingModel


class MemoryVectorRebuildStats(BaseModel):
    """rebuild 実行結果。"""

    model_config = ConfigDict(frozen=True)

    scanned: int = 0
    upserted: int = 0
    unchanged: int = 0
    missing: int = 0
    stale: int = 0
    incompatible: int = 0
    removed_orphans: int = 0


class _EntryState(StrEnum):
    MISSING = "missing"
    STALE = "stale"
    INCOMPATIBLE = "incompatible"
    UNCHANGED = "unchanged"


class MemoryVectorIndexRebuilder:
    """canonical store と派生 vector index を同期する。"""

    def __init__(
        self,
        *,
        store: MutableMemoryStore,
        index: VectorMemoryIndex,
        embedding: EmbeddingModel,
        batch_size: int = 32,
    ) -> None:
        """正本、index、embedding、batch size を注入する。

        Raises:
            ValueError: batch size が正でない場合。
        """
        if batch_size <= 0:
            msg = "Embedding batch_size must be greater than zero"
            raise ValueError(msg)
        self._store = store
        self._index = index
        self._embedding = embedding
        self._batch_size = batch_size

    def rebuild(self, *, remove_orphans: bool = False) -> MemoryVectorRebuildStats:
        """Missing/stale/incompatible entry を同期し統計を返す。

        Returns:
            同期件数の統計。
        """
        records = tuple(self._store.filter(MemoryQuery(text="", limit=1, include_archived=True)))
        canonical_ids = {record.id for record in records}
        classified = tuple((record, self._classify(record)) for record in records)
        stale = [record for record, state in classified if state is not _EntryState.UNCHANGED]
        unchanged = sum(state is _EntryState.UNCHANGED for _, state in classified)
        missing = sum(state is _EntryState.MISSING for _, state in classified)
        stale_count = sum(state is _EntryState.STALE for _, state in classified)
        incompatible = sum(state is _EntryState.INCOMPATIBLE for _, state in classified)

        upserted = 0
        for start in range(0, len(stale), self._batch_size):
            batch = stale[start : start + self._batch_size]
            upserted += self._upsert_batch(tuple(batch))

        removed = 0
        if remove_orphans:
            for memory_id in self._index.ids():
                if memory_id not in canonical_ids:
                    self._index.delete(memory_id)
                    removed += 1
        return MemoryVectorRebuildStats(
            scanned=len(records),
            upserted=upserted,
            unchanged=unchanged,
            missing=missing,
            stale=stale_count,
            incompatible=incompatible,
            removed_orphans=removed,
        )

    def _upsert_batch(self, batch: tuple[MemoryRecord, ...]) -> int:
        """1 batch を検証後に upsert する。

        Returns:
            upsert 件数。

        Raises:
            ValueError: embedding batch の出力数が入力 record 数と一致しない場合。
        """
        vectors = self._embedding.embed_batch(tuple(record.text for record in batch))
        if len(vectors) != len(batch):
            msg = "Embedding batch result length must match input records"
            raise ValueError(msg)
        for record, vector in zip(batch, vectors, strict=False):
            self._index.upsert(
                vector_memory_entry_from_record(
                    record,
                    vector=vector,
                    embedding_provider=self._embedding.provider,
                    embedding_model=self._embedding.model_id,
                    embedding_dimension=self._embedding.dimension,
                )
            )
        return len(batch)

    def _classify(self, record: MemoryRecord) -> _EntryState:
        metadata = self._index.metadata(record.id)
        if metadata is None:
            return _EntryState.MISSING
        if self._is_incompatible(metadata):
            return _EntryState.INCOMPATIBLE
        if metadata.source_digest != memory_record_digest(record):
            return _EntryState.STALE
        return _EntryState.UNCHANGED

    def _is_incompatible(self, metadata: VectorMemoryEntryMetadata) -> bool:
        return (
            metadata.embedding_provider != self._embedding.provider
            or metadata.embedding_model != self._embedding.model_id
            or metadata.embedding_dimension != self._embedding.dimension
        )
