"""SQLiteMemoryStore FTS5 検索と同期のテスト。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.adapters.sqlite.memory_store import SQLiteMemoryStore

if TYPE_CHECKING:
    from pathlib import Path
from iris.contracts.memory import MemoryId, MemoryQuery, MemoryRecord


def _record(memory_id: str, text: str) -> MemoryRecord:
    return MemoryRecord(id=MemoryId(memory_id), text=text)


def test_sqlite_search_fts5_returns_matches(tmp_path: Path) -> None:
    """FTS5 全文検索が一致レコードを返す。"""
    store = SQLiteMemoryStore(tmp_path / "fts.db")
    store.put(_record("m1", "User likes green tea in the morning."))
    store.put(_record("m2", "User prefers coffee after lunch."))
    store.put(_record("m3", "Evening tea is relaxing."))

    results = store.search_fts5(MemoryQuery(text="tea", limit=5))

    ids = [str(r.record.id) for r in results]
    assert "m1" in ids
    assert "m3" in ids
    assert "m2" not in ids


def test_sqlite_search_fts5_filters_archived(tmp_path: Path) -> None:
    """FTS5 検索が archived レコードを除外する。"""
    store = SQLiteMemoryStore(tmp_path / "fts.db")
    store.put(_record("m1", "green tea"))
    store.put(_record("m2", "black tea"))
    store.archive(MemoryId("m2"))

    results = store.search_fts5(MemoryQuery(text="tea", limit=5))
    ids = [str(r.record.id) for r in results]
    assert "m1" in ids
    assert "m2" not in ids


def test_sqlite_search_fts5_respects_limit(tmp_path: Path) -> None:
    """FTS5 検索が limit を尊重する。"""
    store = SQLiteMemoryStore(tmp_path / "fts.db")
    for i in range(10):
        store.put(_record(f"m{i}", f"tea number {i}"))

    results = store.search_fts5(MemoryQuery(text="tea", limit=3))
    assert len(results) <= 3


def test_sqlite_search_fts5_returns_empty_on_zero_limit(tmp_path: Path) -> None:
    """Limit <= 0 で空シーケンスを返す。"""
    store = SQLiteMemoryStore(tmp_path / "fts.db")
    store.put(_record("m1", "tea"))

    assert tuple(store.search_fts5(MemoryQuery(text="tea", limit=0))) == ()


def test_sqlite_search_fts5_syncs_on_update(tmp_path: Path) -> None:
    """Update 後に FTS5 インデックスが同期される。"""
    store = SQLiteMemoryStore(tmp_path / "fts.db")
    store.put(_record("m1", "green tea"))
    store.update(_record("m1", "jasmine tea"))

    results = store.search_fts5(MemoryQuery(text="jasmine", limit=5))
    ids = [str(r.record.id) for r in results]
    assert "m1" in ids


def test_sqlite_search_fts5_syncs_on_archive(tmp_path: Path) -> None:
    """Archive 後も FTS5 インデックスが整合性を保つ。"""
    store = SQLiteMemoryStore(tmp_path / "fts.db")
    store.put(_record("m1", "oolong tea"))
    store.archive(MemoryId("m1"))

    results = store.search_fts5(
        MemoryQuery(text="oolong", limit=5, include_archived=True),
    )
    ids = [str(r.record.id) for r in results]
    assert "m1" in ids
