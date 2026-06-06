"""SQLiteMemoryStore tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.adapters.memory.sqlite import SQLiteMemoryStore
from iris.contracts.memory import (
    MemoryId,
    MemoryKind,
    MemoryQuery,
    MemoryRecord,
)
from iris.core.ids import ActorId, ObservationId, SpaceId

if TYPE_CHECKING:
    from pathlib import Path

from tests.helpers.approx import approx


def _record(
    memory_id: str,
    text: str = "memory",
    *,
    actor_id: str | None = None,
    space_id: str | None = None,
    kind: MemoryKind = MemoryKind.NOTE,
    archived: bool = False,
) -> MemoryRecord:
    return MemoryRecord(
        id=MemoryId(memory_id),
        text=text,
        actor_id=ActorId(actor_id) if actor_id else None,
        space_id=SpaceId(space_id) if space_id else None,
        kind=kind,
        archived=archived,
    )


def test_sqlite_memory_store_put_and_get(tmp_path: Path) -> None:
    """Put と get がレコードを往復できることを確認する。"""
    store = SQLiteMemoryStore(tmp_path / "memories.db")

    record = _record("m1", "User likes jasmine tea.")
    store.put(record)

    fetched = store.get(MemoryId("m1"))
    assert fetched is not None
    assert fetched.text == "User likes jasmine tea."
    assert fetched.kind == MemoryKind.NOTE
    assert fetched.archived is False


def test_sqlite_memory_store_persists_metadata_and_kind(tmp_path: Path) -> None:
    """Metadata と kind が永続化されることを確認する。"""
    store = SQLiteMemoryStore(tmp_path / "memories.db")

    record = MemoryRecord(
        id=MemoryId("m1"),
        text="favorite drink: tea",
        kind=MemoryKind.PREFERENCE,
        confidence=0.8,
        source_observation_id=ObservationId("obs-1"),
        metadata={"channel": "discord", "lang": "ja"},
    )
    store.put(record)

    fetched = store.get(MemoryId("m1"))
    assert fetched is not None
    assert fetched.kind == MemoryKind.PREFERENCE
    assert fetched.confidence == approx(0.8)
    assert fetched.source_observation_id == ObservationId("obs-1")
    assert dict(fetched.metadata) == {"channel": "discord", "lang": "ja"}


def test_sqlite_memory_store_survives_reinstantiation(tmp_path: Path) -> None:
    """レコードを永続化し、新しいインスタンスで再読み込みできることを確認する。"""
    db_path = tmp_path / "memories.db"
    store1 = SQLiteMemoryStore(db_path)
    store1.put(_record("m1", "first memory"))

    store2 = SQLiteMemoryStore(db_path)
    fetched = store2.get(MemoryId("m1"))
    assert fetched is not None
    assert fetched.text == "first memory"


def test_sqlite_memory_store_update_upserts(tmp_path: Path) -> None:
    """Update が upsert として動作することを確認する。"""
    store = SQLiteMemoryStore(tmp_path / "memories.db")
    store.put(_record("m1", "first"))

    store.update(_record("m1", "second", kind=MemoryKind.FACT))
    fetched = store.get(MemoryId("m1"))
    assert fetched is not None
    assert fetched.text == "second"
    assert fetched.kind == MemoryKind.FACT


def test_sqlite_memory_store_update_creates_new(tmp_path: Path) -> None:
    """Update が存在しない ID に新規作成できることを確認する。"""
    store = SQLiteMemoryStore(tmp_path / "memories.db")
    store.update(_record("m1", "created via update"))

    assert store.get(MemoryId("m1")) is not None


def test_sqlite_memory_store_archive_toggles_flag(tmp_path: Path) -> None:
    """Archive が archived フラグを切り替え、永続化されることを確認する。"""
    store = SQLiteMemoryStore(tmp_path / "memories.db")
    store.put(_record("m1", "tea"))

    archived = store.archive(MemoryId("m1"))
    assert archived is not None
    assert archived.archived is True

    fetched = store.get(MemoryId("m1"))
    assert fetched is not None
    assert fetched.archived is True

    unarchived = store.archive(MemoryId("m1"), archived=False)
    assert unarchived is not None
    assert unarchived.archived is False


def test_sqlite_memory_store_archive_returns_none_for_missing(tmp_path: Path) -> None:
    """存在しない ID の archive は None を返す。"""
    store = SQLiteMemoryStore(tmp_path / "memories.db")

    assert store.archive(MemoryId("missing")) is None


def test_sqlite_memory_store_filter_by_actor_and_kind(tmp_path: Path) -> None:
    """Filter が actor_id / space_id / kind で絞り込めることを確認する。"""
    store = SQLiteMemoryStore(tmp_path / "memories.db")
    store.put(_record("m1", "alice tea", actor_id="alice", kind=MemoryKind.PREFERENCE))
    store.put(_record("m2", "bob tea", actor_id="bob", kind=MemoryKind.PREFERENCE))
    store.put(_record("m3", "alice fact", actor_id="alice", kind=MemoryKind.FACT))

    results = store.filter(
        MemoryQuery(text="", actor_id=ActorId("alice"), kind=MemoryKind.PREFERENCE)
    )

    ids = tuple(record.id for record in results)
    assert ids == (MemoryId("m1"),)


def test_sqlite_memory_store_filter_excludes_archived_by_default(tmp_path: Path) -> None:
    """Filter はデフォルトで archived を除外する。"""
    store = SQLiteMemoryStore(tmp_path / "memories.db")
    store.put(_record("m1", "active", actor_id="alice"))
    store.put(_record("m2", "stale", actor_id="alice", archived=True))

    active = store.filter(MemoryQuery(text="", actor_id=ActorId("alice")))
    all_results = store.filter(
        MemoryQuery(text="", actor_id=ActorId("alice"), include_archived=True)
    )

    assert tuple(r.id for r in active) == (MemoryId("m1"),)
    assert {r.id for r in all_results} == {MemoryId("m1"), MemoryId("m2")}


def test_sqlite_memory_store_search_ranks_token_overlap(tmp_path: Path) -> None:
    """Search がトークン重複カウントでランク付けすることを確認する。"""
    store = SQLiteMemoryStore(tmp_path / "memories.db")
    store.put(_record("m1", "User likes green tea."))
    store.put(_record("m2", "User likes tea and quiet mornings."))
    store.put(_record("m3", "Unrelated memory."))

    results = store.search(MemoryQuery(text="quiet tea", limit=2))

    assert tuple(r.record.id for r in results) == (MemoryId("m2"), MemoryId("m1"))
    assert tuple(r.score for r in results) == (2.0, 1.0)


def test_sqlite_memory_store_search_filters_archived(tmp_path: Path) -> None:
    """Search が archived を除外してランク付けすることを確認する。"""
    store = SQLiteMemoryStore(tmp_path / "memories.db")
    store.put(_record("m1", "tea memory"))
    store.put(_record("m2", "tea memory archived", archived=True))

    results = store.search(MemoryQuery(text="tea"))

    assert tuple(r.record.id for r in results) == (MemoryId("m1"),)


def test_sqlite_memory_store_returns_empty_on_zero_limit(tmp_path: Path) -> None:
    """Limit <= 0 で空シーケンスを返す。"""
    store = SQLiteMemoryStore(tmp_path / "memories.db")
    store.put(_record("m1", "tea"))

    assert tuple(store.search(MemoryQuery(text="tea", limit=0))) == ()


def test_sqlite_memory_store_creates_parent_dir(tmp_path: Path) -> None:
    """深いパスでも親ディレクトリを自動作成する。"""
    db_path = tmp_path / "nested" / "deep" / "memories.db"
    SQLiteMemoryStore(db_path)

    assert db_path.exists()
