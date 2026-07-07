"""MemoryVectorIndexRebuilder のテスト。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from iris.adapters.embeddings.fake import DeterministicFakeEmbedding
from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.adapters.memory.vector_index import InMemoryVectorMemoryIndex
from iris.adapters.persistence.sqlite.stores.memory import SQLiteMemoryStore
from iris.cognitive.memory.hybrid import HybridMemoryRetriever
from iris.contracts.memory import (
    MemoryId,
    MemoryQuery,
    MemoryRecord,
    VectorMemoryEntry,
    memory_record_digest,
)
from iris.runtime.memory_vector_rebuilder import MemoryVectorIndexRebuilder
from iris.runtime.wiring.memory import SQLiteFTS5MemoryRetriever

if TYPE_CHECKING:
    from pathlib import Path


class _TeaEmbedding:
    provider = "test"
    model_id = "tea-alias-v1"
    dimension = 2

    def embed(self, text: str) -> tuple[float, float]:
        """Tea/sencha alias を同じ vector に写像する。

        Returns:
            2次元 test vector。
        """
        normalized = text.casefold()
        return (1.0, 0.0) if "tea" in normalized or "sencha" in normalized else (0.0, 1.0)

    def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, float], ...]:
        """入力順の test vector を返す。

        Returns:
            入力順の2次元 vector。
        """
        return tuple(self.embed(text) for text in texts)


class _ShortBatchEmbedding:
    provider = "test"
    model_id = "short-batch"
    dimension = 2

    def embed(self, text: str) -> tuple[float, float]:
        """単一 test vector を返す。

        Returns:
            2次元 test vector。
        """
        return (1.0, 0.0) if text else (0.0, 1.0)

    def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, float], ...]:
        """入力より短い batch result を返す。

        Returns:
            入力より短い test vector 群。
        """
        if not texts:
            return ()
        return ((1.0, 0.0),)


@dataclass(frozen=True)
class _EntryOverrides:
    digest: str | None = None
    provider: str | None = None
    model: str | None = None
    dimension: int | None = None


_DEFAULT_ENTRY_OVERRIDES = _EntryOverrides()


def test_rebuild_is_idempotent_and_repairs_stale_entries() -> None:
    """初回同期後の再実行は upsert せず、正本更新後だけ再同期する。"""
    store = InMemoryMemoryStore()
    store.put(MemoryRecord(id=MemoryId("m1"), text="green tea"))
    index = InMemoryVectorMemoryIndex()
    embedding = DeterministicFakeEmbedding(dimension=8)
    rebuilder = MemoryVectorIndexRebuilder(
        store=store, index=index, embedding=embedding, batch_size=2
    )

    first = rebuilder.rebuild()
    second = rebuilder.rebuild()
    store.update(MemoryRecord(id=MemoryId("m1"), text="black coffee"))
    third = rebuilder.rebuild()

    assert (first.scanned, first.upserted, first.unchanged) == (1, 1, 0)
    assert (second.scanned, second.upserted, second.unchanged) == (1, 0, 1)
    assert (third.scanned, third.upserted, third.unchanged) == (1, 1, 0)


def test_rebuild_removes_orphans_when_requested() -> None:
    """remove_orphans=True の場合だけ正本にない entry を削除する。"""
    store = InMemoryMemoryStore()
    index = InMemoryVectorMemoryIndex()
    embedding = DeterministicFakeEmbedding(dimension=4)
    index.upsert(
        VectorMemoryEntry(
            memory_id=MemoryId("orphan"),
            vector=embedding.embed("orphan"),
            source_digest="old",
            embedding_provider=embedding.provider,
            embedding_model=embedding.model_id,
            embedding_dimension=embedding.dimension,
        )
    )
    rebuilder = MemoryVectorIndexRebuilder(store=store, index=index, embedding=embedding)

    kept = rebuilder.rebuild()
    removed = rebuilder.rebuild(remove_orphans=True)

    assert kept.removed_orphans == 0
    assert removed.removed_orphans == 1
    assert index.ids() == ()


def test_rebuild_classifies_missing_stale_and_incompatible_entries() -> None:
    """Rebuild stats は同期理由を個別に計上する。"""
    records = tuple(
        MemoryRecord(id=MemoryId(memory_id), text=text)
        for memory_id, text in (
            ("missing", "missing tea"),
            ("stale", "fresh coffee"),
            ("model", "model changed"),
            ("dimension", "dimension changed"),
            ("provider", "provider changed"),
            ("unchanged", "same record"),
        )
    )
    store = InMemoryMemoryStore()
    for record in records:
        store.put(record)
    embedding = DeterministicFakeEmbedding(model="fake-v2", dimension=4)
    index = InMemoryVectorMemoryIndex()
    _upsert_test_entry(index, records[1], embedding, _EntryOverrides(digest="old-digest"))
    _upsert_test_entry(index, records[2], embedding, _EntryOverrides(model="fake-v1"))
    _upsert_test_entry(index, records[3], embedding, _EntryOverrides(dimension=3))
    _upsert_test_entry(index, records[4], embedding, _EntryOverrides(provider="other"))
    _upsert_test_entry(index, records[5], embedding)

    stats = MemoryVectorIndexRebuilder(store=store, index=index, embedding=embedding).rebuild()

    assert stats.scanned == 6
    assert stats.upserted == 5
    assert stats.missing == 1
    assert stats.stale == 1
    assert stats.incompatible == 3
    assert stats.unchanged == 1
    provider_metadata = index.metadata(MemoryId("provider"))
    assert provider_metadata is not None
    assert provider_metadata.embedding_provider == "fake"


def test_rebuild_rejects_batch_length_mismatch_before_partial_upsert() -> None:
    """Embedding batch length mismatch は partial upsert 前に失敗する。"""
    store = InMemoryMemoryStore()
    store.put(MemoryRecord(id=MemoryId("m1"), text="green tea"))
    store.put(MemoryRecord(id=MemoryId("m2"), text="black tea"))
    index = InMemoryVectorMemoryIndex()
    rebuilder = MemoryVectorIndexRebuilder(
        store=store,
        index=index,
        embedding=_ShortBatchEmbedding(),
        batch_size=2,
    )

    with pytest.raises(
        ValueError,
        match="Embedding batch result length must match input records",
    ):
        rebuilder.rebuild()
    assert index.ids() == ()


def _upsert_test_entry(
    index: InMemoryVectorMemoryIndex,
    record: MemoryRecord,
    embedding: DeterministicFakeEmbedding,
    overrides: _EntryOverrides = _DEFAULT_ENTRY_OVERRIDES,
) -> None:
    """指定 compatibility metadata の test entry を登録する。"""
    entry_dimension = overrides.dimension or embedding.dimension
    index.upsert(
        VectorMemoryEntry(
            memory_id=record.id,
            vector=embedding.embed(record.text)[:entry_dimension],
            source_digest=overrides.digest or memory_record_digest(record),
            embedding_provider=overrides.provider or embedding.provider,
            embedding_model=overrides.model or embedding.model_id,
            embedding_dimension=entry_dimension,
        )
    )


def test_rebuild_restores_vector_backed_hybrid_retrieval_after_restart(
    tmp_path: Path,
) -> None:
    """Process-local index喪失後も正本SQLiteからvector recallを復元する。"""
    store = SQLiteMemoryStore(tmp_path / "restart-memory.db")
    memory_id = MemoryId("tea-memory")
    store.put(MemoryRecord(id=memory_id, text="User likes green tea."))
    fts = SQLiteFTS5MemoryRetriever(store)
    query = MemoryQuery(text="sencha", limit=5)
    assert fts.search(query) == ()

    rebuilt_index = InMemoryVectorMemoryIndex()
    embedding = _TeaEmbedding()
    stats = MemoryVectorIndexRebuilder(
        store=store,
        index=rebuilt_index,
        embedding=embedding,
    ).rebuild()
    hybrid = HybridMemoryRetriever(
        fts_retriever=fts,
        vector_index=rebuilt_index,
        embedding=embedding,
        store=store,
    )

    results = hybrid.search(query)

    assert stats.missing == 1
    assert stats.upserted == 1
    assert [result.record.id for result in results] == [memory_id]
