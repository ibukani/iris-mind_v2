"""MemoryVectorIndexRebuilder のテスト。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from iris.adapters.embeddings.fake import DeterministicFakeEmbedding
from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.adapters.memory.vector_index import InMemoryVectorMemoryIndex
from iris.adapters.persistence.sqlite.stores.memory import SQLiteMemoryStore
from iris.cognitive.memory.hybrid import HybridMemoryRetriever
from iris.contracts.embeddings import (
    EmbeddingBatchRequest,
    EmbeddingBatchResult,
    EmbeddingRequest,
    EmbeddingResult,
)
from iris.contracts.memory import (
    MemoryId,
    MemoryQuery,
    MemoryRecord,
    VectorMemoryEntry,
    memory_record_digest,
)
from iris.contracts.model_invocation import ModelInvocationMetadata
from iris.contracts.model_policy import ModelCallKind
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

    def embed_text(self, request: EmbeddingRequest) -> EmbeddingResult:
        """EmbeddingClient contract の単一 result を返す。

        Returns:
            EmbeddingResult: test vector。
        """
        return EmbeddingResult(
            vector=self.embed(request.text),
            dimension=self.dimension,
            reason="tea alias test embedding",
            model_metadata=_tea_embedding_metadata(request.model_slot),
            metadata=request.metadata,
        )

    def embed_text_batch(self, request: EmbeddingBatchRequest) -> EmbeddingBatchResult:
        """EmbeddingClient contract の batch result を返す。

        Returns:
            EmbeddingBatchResult: 入力順の test vectors。
        """
        metadata = _tea_embedding_metadata(request.model_slot)
        return EmbeddingBatchResult(
            embeddings=tuple(
                EmbeddingResult(
                    vector=self.embed(text),
                    dimension=self.dimension,
                    reason="tea alias test embedding",
                    model_metadata=metadata,
                )
                for text in request.texts
            ),
            reason="tea alias test embedding batch",
            model_metadata=metadata,
            metadata=request.metadata,
        )


def _tea_embedding_metadata(model_slot: str | None = None) -> ModelInvocationMetadata:
    return ModelInvocationMetadata(
        call_kind=ModelCallKind.EMBEDDING,
        provider="test",
        model_name="tea-alias-v1",
        adapter_name="tea_alias_test_embedding",
        model_slot=model_slot,
    )


class _CountingEmbedding(DeterministicFakeEmbedding):
    """Batch embedding 呼び出し回数を記録する fake。"""

    def __init__(self) -> None:
        """既定 fake embedding と call counter を初期化する。"""
        super().__init__(dimension=4)
        self.batch_calls = 0

    @override
    def embed_text_batch(self, request: EmbeddingBatchRequest) -> EmbeddingBatchResult:
        """Batch embedding の呼び出し回数を増やしてから委譲する。

        Returns:
            EmbeddingBatchResult: DeterministicFakeEmbedding の batch result。
        """
        self.batch_calls += 1
        return super().embed_text_batch(request)


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


def test_rebuild_skips_cached_unchanged_records_without_reembedding() -> None:
    """Vector metadata が有効なら同じ memory record を再 embedding しない。"""
    store = InMemoryMemoryStore()
    store.put(MemoryRecord(id=MemoryId("m1"), text="green tea"))
    index = InMemoryVectorMemoryIndex()
    embedding = _CountingEmbedding()
    rebuilder = MemoryVectorIndexRebuilder(store=store, index=index, embedding=embedding)

    first = rebuilder.rebuild()
    second = rebuilder.rebuild()
    store.update(MemoryRecord(id=MemoryId("m1"), text="green tea updated"))
    third = rebuilder.rebuild()

    assert first.upserted == 1
    assert second.unchanged == 1
    assert third.stale == 1
    assert embedding.batch_calls == 2


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
