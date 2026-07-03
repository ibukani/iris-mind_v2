"""SQLite schema migration tests。"""

from __future__ import annotations

import contextlib
import sqlite3
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import create_engine

from iris.adapters.persistence.sqlite.migrations import available_migrations
from iris.adapters.persistence.sqlite.migrations.v0001_baseline import BASELINE_V1
from iris.adapters.persistence.sqlite.migrator import (
    SQLiteCorruptDatabaseError,
    SQLiteLegacySchemaError,
    SQLiteMigrationError,
    SQLiteMigrationHistoryError,
    SQLiteMigrationStatus,
    SQLiteSchemaMigrator,
    SQLiteUnsupportedSchemaVersionError,
)
from iris.adapters.persistence.sqlite.migrator_types import SQLiteMigration
from iris.adapters.persistence.sqlite.schema import Base
from iris.adapters.persistence.sqlite.schema.version import CURRENT_SQLITE_SCHEMA_VERSION

if TYPE_CHECKING:
    from pathlib import Path


def test_empty_db_initializes_to_current_schema(tmp_path: Path) -> None:
    """空 DB は current schema version に初期化される。"""
    db_path = tmp_path / "state.sqlite3"

    result = SQLiteSchemaMigrator().ensure_current(db_path)

    assert result.status is SQLiteMigrationStatus.INITIALIZED
    assert result.previous_version == 0
    assert result.current_version == CURRENT_SQLITE_SCHEMA_VERSION
    assert result.applied_versions == (1, 2, 3, 4)
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        assert _user_version(conn) == CURRENT_SQLITE_SCHEMA_VERSION
        assert _table_exists(conn, "accounts")
        assert _table_exists(conn, "memories")
        assert _table_exists(conn, "memories_fts5")
        assert _table_exists(conn, "delivery_outbox")
        assert _table_exists(conn, "background_jobs")
        assert _table_exists(conn, "memory_candidate_reviews")
        assert _table_exists(conn, "conversation_transcripts")
        assert _table_exists(conn, "safety_audit_records")
        assert _latest_migration(conn) == "safety_audit_records"


def test_existing_unversioned_memory_db_upgrades_and_rebuilds_fts5(tmp_path: Path) -> None:
    """既存 unversioned DB は v1 に adopt され、FTS5 index も作られる。"""
    db_path = tmp_path / "legacy.sqlite3"
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        _create_memory_table(conn)
        conn.execute(
            """
            INSERT INTO memories(memory_id, text, kind, metadata_json)
            VALUES ('m1', 'green tea memory', 'semantic', '{}')
            """
        )
        conn.commit()

    result = SQLiteSchemaMigrator().ensure_current(db_path)

    assert result.status is SQLiteMigrationStatus.INITIALIZED
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        assert _user_version(conn) == CURRENT_SQLITE_SCHEMA_VERSION
        row = conn.execute(
            """
            SELECT memory_id
            FROM memories_fts5
            WHERE memories_fts5 MATCH 'tea'
            """
        ).fetchone()
        assert row is not None
        assert row[0] == "m1"


def test_existing_unversioned_sqlalchemy_db_upgrades_with_manual_memory_table(
    tmp_path: Path,
) -> None:
    """既存 create_all schema と manual memory table を v1 として adopt できる。"""
    db_path = tmp_path / "legacy-create-all.sqlite3"
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        _create_memory_table(conn)
        conn.execute(
            """
            INSERT INTO memories(memory_id, text, kind, metadata_json)
            VALUES ('m1', 'alchemy legacy memory', 'semantic', '{}')
            """
        )
        conn.commit()

    result = SQLiteSchemaMigrator().ensure_current(db_path)

    assert result.status is SQLiteMigrationStatus.INITIALIZED
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        assert _user_version(conn) == CURRENT_SQLITE_SCHEMA_VERSION
        assert _table_exists(conn, "accounts")
        assert _table_exists(conn, "memories_fts5")
        assert _table_exists(conn, "relationship_snapshots")
        assert _table_exists(conn, "activity_events")
        assert _table_exists(conn, "delivery_outbox")
        assert _table_exists(conn, "background_jobs")
        assert _table_exists(conn, "memory_candidate_reviews")
        assert _table_exists(conn, "conversation_transcripts")
        assert _table_exists(conn, "safety_audit_records")
        assert _table_exists(conn, "scheduler_targets")
        row = conn.execute(
            """
            SELECT memory_id
            FROM memories_fts5
            WHERE memories_fts5 MATCH 'legacy'
            """
        ).fetchone()
        assert row is not None
        assert row[0] == "m1"


def test_existing_v1_db_upgrades_to_current_schema(tmp_path: Path) -> None:
    """既存 v1 DB は v2/v3/v4 migration を追加適用する。"""
    db_path = tmp_path / "v1.sqlite3"
    _create_v1_database(db_path)

    result = SQLiteSchemaMigrator().ensure_current(db_path)

    assert result.status is SQLiteMigrationStatus.UPGRADED
    assert result.previous_version == 1
    assert result.applied_versions == (2, 3, 4)
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        assert _user_version(conn) == CURRENT_SQLITE_SCHEMA_VERSION
        assert _table_exists(conn, "background_jobs")
        assert _table_exists(conn, "memory_candidate_reviews")
        assert _table_exists(conn, "conversation_transcripts")
        assert _table_exists(conn, "safety_audit_records")
        assert _migration_names(conn) == (
            "baseline_runtime_state",
            "runtime_learning_state",
            "conversation_transcripts",
            "safety_audit_records",
        )


def test_already_current_db_does_not_reapply_migrations(tmp_path: Path) -> None:
    """Current DB では migration history が増えない。"""
    db_path = tmp_path / "state.sqlite3"
    migrator = SQLiteSchemaMigrator()
    migrator.ensure_current(db_path)

    second = migrator.ensure_current(db_path)

    assert second.status is SQLiteMigrationStatus.ALREADY_CURRENT
    assert second.applied_versions == ()
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()
        assert count is not None
        assert count[0] == 4


def test_migration_order_is_stable() -> None:
    """Migration 定義は version 昇順で安定する。"""
    versions = tuple(migration.version for migration in available_migrations())

    assert versions == tuple(sorted(versions))
    assert versions == tuple(range(1, CURRENT_SQLITE_SCHEMA_VERSION + 1))


def test_failed_migration_does_not_advance_user_version(tmp_path: Path) -> None:
    """失敗 migration は user_version を進めない。"""
    db_path = tmp_path / "broken.sqlite3"
    migrator = SQLiteSchemaMigrator(
        migrations=(
            SQLiteMigration(
                version=1,
                name="broken",
                statements=(
                    "CREATE TABLE created_before_failure (id TEXT PRIMARY KEY)",
                    "INSERT INTO missing_table(id) VALUES ('x')",
                ),
            ),
        )
    )

    with pytest.raises(SQLiteMigrationError):
        migrator.ensure_current(db_path)

    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        assert _user_version(conn) == 0
        assert not _table_exists(conn, "created_before_failure")


def test_unsupported_future_schema_version_fails_closed(tmp_path: Path) -> None:
    """Future schema version は silent open しない。"""
    db_path = tmp_path / "future.sqlite3"
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        conn.execute("PRAGMA user_version = 99")
        conn.commit()

    with pytest.raises(SQLiteUnsupportedSchemaVersionError):
        SQLiteSchemaMigrator().ensure_current(db_path)


def test_incompatible_unversioned_schema_fails_closed(tmp_path: Path) -> None:
    """既存 table が required column を欠く場合は fail closed。"""
    db_path = tmp_path / "bad-legacy.sqlite3"
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        conn.execute("CREATE TABLE memories (memory_id TEXT PRIMARY KEY)")
        conn.commit()

    with pytest.raises(SQLiteLegacySchemaError):
        SQLiteSchemaMigrator().ensure_current(db_path)

    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        assert _user_version(conn) == 0


def test_current_schema_without_fts5_fails_closed(tmp_path: Path) -> None:
    """user_version だけ current でも memories_fts5 がなければ open しない。"""
    db_path = tmp_path / "missing-fts.sqlite3"
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        _create_memory_table(conn)
        conn.execute(
            """
            CREATE TABLE schema_migrations(
                version INTEGER PRIMARY KEY,
                name TEXT,
                checksum TEXT,
                applied_at TEXT
            )
            """,
        )
        conn.execute(f"PRAGMA user_version = {CURRENT_SQLITE_SCHEMA_VERSION}")
        conn.commit()

    with pytest.raises(SQLiteLegacySchemaError, match="memories_fts5"):
        SQLiteSchemaMigrator().ensure_current(db_path)


def test_current_schema_with_checksum_mismatch_fails_closed(tmp_path: Path) -> None:
    """schema_migrations の checksum が合わない DB は trusted current としない。"""
    db_path = tmp_path / "bad-history.sqlite3"
    SQLiteSchemaMigrator().ensure_current(db_path)
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        conn.execute("UPDATE schema_migrations SET checksum = 'not-the-current-checksum'")
        conn.commit()

    with pytest.raises(SQLiteMigrationHistoryError, match="not trusted"):
        SQLiteSchemaMigrator().ensure_current(db_path)


def test_corrupt_db_fails_closed_without_recreate(tmp_path: Path) -> None:
    """Corrupt DB は silent delete / recreate せず fail closed する。"""
    db_path = tmp_path / "corrupt.sqlite3"
    db_path.write_bytes(b"not a sqlite database")

    with pytest.raises(SQLiteCorruptDatabaseError, match="Original DB was left untouched"):
        SQLiteSchemaMigrator().ensure_current(db_path)

    assert db_path.read_bytes() == b"not a sqlite database"


def _create_v1_database(db_path: Path) -> None:
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        for statement in BASELINE_V1.statements:
            conn.execute(statement)
        conn.execute(
            """
            INSERT INTO schema_migrations(version, name, checksum, applied_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                BASELINE_V1.version,
                BASELINE_V1.name,
                BASELINE_V1.checksum,
                "2026-07-01T00:00:00+00:00",
            ),
        )
        conn.execute("PRAGMA user_version = 1")
        conn.commit()


def _create_memory_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE memories (
            memory_id TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            actor_id TEXT,
            space_id TEXT,
            salience REAL NOT NULL DEFAULT 0.0,
            kind TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 1.0,
            source_observation_id TEXT,
            created_at TEXT,
            updated_at TEXT,
            archived INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """,
    )


def _user_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    assert row is not None
    return int(row[0])


def _migration_names(conn: sqlite3.Connection) -> tuple[str, ...]:
    rows = conn.execute("SELECT name FROM schema_migrations ORDER BY version").fetchall()
    return tuple(str(row[0]) for row in rows)


def _latest_migration(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT name FROM schema_migrations ORDER BY version DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    return str(row[0])


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name = ? AND type = 'table'",
        (table_name,),
    ).fetchone()
    return row is not None
