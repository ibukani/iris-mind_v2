"""MemoryVectorIndexRebuilder のテスト。"""

from __future__ import annotations

from iris.adapters.embeddings.fake import DeterministicFakeEmbedding
from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.adapters.memory.vector_index import InMemoryVectorMemoryIndex
from iris.contracts.memory import (
    MemoryId,
    MemoryRecord,
    VectorMemoryEntry,
    memory_record_digest,
)
from iris.runtime.memory_vector_rebuilder import MemoryVectorIndexRebuilder


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
            ("incompatible", "model changed"),
            ("unchanged", "same record"),
        )
    )
    store = InMemoryMemoryStore()
    for record in records:
        store.put(record)
    embedding = DeterministicFakeEmbedding(model="fake-v2", dimension=4)
    index = InMemoryVectorMemoryIndex()
    _upsert_test_entry(index, records[1], embedding, digest="old-digest")
    _upsert_test_entry(index, records[2], embedding, model="fake-v1")
    _upsert_test_entry(index, records[3], embedding)

    stats = MemoryVectorIndexRebuilder(store=store, index=index, embedding=embedding).rebuild()

    assert stats.scanned == 4
    assert stats.upserted == 3
    assert stats.missing == 1
    assert stats.stale == 1
    assert stats.incompatible == 1
    assert stats.unchanged == 1


def _upsert_test_entry(
    index: InMemoryVectorMemoryIndex,
    record: MemoryRecord,
    embedding: DeterministicFakeEmbedding,
    *,
    digest: str | None = None,
    model: str | None = None,
) -> None:
    """指定 compatibility metadata の test entry を登録する。"""
    index.upsert(
        VectorMemoryEntry(
            memory_id=record.id,
            vector=embedding.embed(record.text),
            source_digest=digest or memory_record_digest(record),
            embedding_model=model or embedding.model_id,
            embedding_dimension=embedding.dimension,
        )
    )
