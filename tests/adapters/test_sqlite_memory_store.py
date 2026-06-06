"""SQLiteMemoryStore tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import sqlite3
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


def test_sqlite_memory_store_put_populates_timestamps(tmp_path: Path) -> None:
    """Put 時に created_at と updated_at が UTC で自動設定されることを確認する。"""
    store = SQLiteMemoryStore(tmp_path / "memories.db")
    before = datetime.now(tz=UTC)

    store.put(_record("m1", "tea preference"))

    after = datetime.now(tz=UTC)
    fetched = store.get(MemoryId("m1"))
    assert fetched is not None
    assert fetched.created_at is not None
    assert fetched.updated_at is not None
    assert before - timedelta(seconds=1) <= fetched.created_at <= after + timedelta(seconds=1)
    assert fetched.created_at == fetched.updated_at


def test_sqlite_memory_store_put_preserves_explicit_timestamps(tmp_path: Path) -> None:
    """Put 時に明示された created_at / updated_at は上書きしないことを確認する。"""
    store = SQLiteMemoryStore(tmp_path / "memories.db")
    created = datetime(2026, 1, 1, tzinfo=UTC)
    updated = datetime(2026, 2, 2, tzinfo=UTC)

    store.put(
        MemoryRecord(
            id=MemoryId("m1"),
            text="explicit timestamps",
            created_at=created,
            updated_at=updated,
        )
    )

    fetched = store.get(MemoryId("m1"))
    assert fetched is not None
    assert fetched.created_at == created
    assert fetched.updated_at == updated


def test_sqlite_memory_store_update_preserves_created_at_and_advances_updated_at(
    tmp_path: Path,
) -> None:
    """Update 時に created_at を保持し、updated_at のみ進めることを確認する。"""
    store = SQLiteMemoryStore(tmp_path / "memories.db")
    initial = _record("m1", "first")
    store.put(initial)
    original = store.get(MemoryId("m1"))
    assert original is not None
    assert original.created_at is not None
    assert original.updated_at is not None

    before_update = datetime.now(tz=UTC)
    store.update(_record("m1", "second", kind=MemoryKind.FACT))
    after_update = datetime.now(tz=UTC)

    fetched = store.get(MemoryId("m1"))
    assert fetched is not None
    assert fetched.created_at == original.created_at
    assert fetched.updated_at is not None
    assert fetched.updated_at >= original.updated_at
    assert (
        before_update - timedelta(seconds=1)
        <= fetched.updated_at
        <= after_update + timedelta(seconds=1)
    )


def test_sqlite_memory_store_update_keeps_explicit_updated_at(tmp_path: Path) -> None:
    """Update 時に明示された updated_at は上書きしないことを確認する。"""
    store = SQLiteMemoryStore(tmp_path / "memories.db")
    store.put(_record("m1", "first"))

    explicit_updated = datetime(2027, 5, 5, tzinfo=UTC)
    store.update(
        MemoryRecord(
            id=MemoryId("m1"),
            text="second with explicit updated_at",
            updated_at=explicit_updated,
        )
    )

    fetched = store.get(MemoryId("m1"))
    assert fetched is not None
    assert fetched.updated_at == explicit_updated


def test_sqlite_memory_store_update_fills_created_at_from_existing(tmp_path: Path) -> None:
    """Update 時に record.created_at 未指定なら既存 created_at を引き継ぐことを確認する。"""
    store = SQLiteMemoryStore(tmp_path / "memories.db")
    store.put(_record("m1", "first"))
    original = store.get(MemoryId("m1"))
    assert original is not None
    assert original.created_at is not None

    store.update(MemoryRecord(id=MemoryId("m1"), text="second without created_at"))

    fetched = store.get(MemoryId("m1"))
    assert fetched is not None
    assert fetched.created_at == original.created_at


def test_sqlite_memory_store_archive_advances_updated_at(tmp_path: Path) -> None:
    """Archive 時に archived フラグが切り替わり updated_at が進められることを確認する。"""
    store = SQLiteMemoryStore(tmp_path / "memories.db")
    store.put(_record("m1", "tea"))
    original = store.get(MemoryId("m1"))
    assert original is not None
    assert original.updated_at is not None

    before_archive = datetime.now(tz=UTC)
    archived = store.archive(MemoryId("m1"))
    after_archive = datetime.now(tz=UTC)

    assert archived is not None
    assert archived.archived is True
    assert archived.updated_at is not None
    assert archived.updated_at > original.updated_at
    assert before_archive - timedelta(seconds=1) <= archived.updated_at
    assert archived.updated_at <= after_archive + timedelta(seconds=1)

    before_unarchive = datetime.now(tz=UTC)
    unarchived = store.archive(MemoryId("m1"), archived=False)
    after_unarchive = datetime.now(tz=UTC)
    assert unarchived is not None
    assert unarchived.archived is False
    assert unarchived.updated_at is not None
    assert unarchived.updated_at >= archived.updated_at
    assert before_unarchive - timedelta(seconds=1) <= unarchived.updated_at
    assert unarchived.updated_at <= after_unarchive + timedelta(seconds=1)


def test_sqlite_memory_store_archive_keeps_explicit_updated_at(tmp_path: Path) -> None:
    """Archive 経路の UTC 正規化で明示 updated_at が上書きされることを確認する。"""
    store = SQLiteMemoryStore(tmp_path / "memories.db")
    explicit_updated = datetime(2026, 3, 3, tzinfo=UTC)
    store.put(
        MemoryRecord(
            id=MemoryId("m1"),
            text="tea",
            created_at=explicit_updated,
            updated_at=explicit_updated,
        )
    )

    archived = store.archive(MemoryId("m1"))
    assert archived is not None
    assert archived.archived is True
    assert archived.updated_at is not None
    assert archived.updated_at > explicit_updated


def test_sqlite_memory_store_creates_filter_indexes(tmp_path: Path) -> None:
    """_init_db で filter 用インデックスが作成されることを確認する。"""
    db_path = tmp_path / "memories.db"
    SQLiteMemoryStore(db_path)

    conn = sqlite3.connect(db_path)
    try:
        index_names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'memories'"
            )
        }
    finally:
        conn.close()

    assert "idx_memories_actor_id" in index_names
    assert "idx_memories_space_id" in index_names
    assert "idx_memories_kind" in index_names
    assert "idx_memories_archived" in index_names
