"""SQLite schema migration runner。"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
import sqlite3
from typing import TYPE_CHECKING

from iris.adapters.persistence.sqlite.migrations.registry import available_migrations
from iris.adapters.persistence.sqlite.schema.background_jobs import (
    BACKGROUND_JOB_REQUIRED_COLUMNS,
)
from iris.adapters.persistence.sqlite.schema.memory_candidate_reviews import (
    MEMORY_CANDIDATE_REVIEW_REQUIRED_COLUMNS,
)
from iris.adapters.persistence.sqlite.schema.transcript import (
    CONVERSATION_TRANSCRIPT_REQUIRED_COLUMNS,
)
from iris.adapters.persistence.sqlite.schema.version import CURRENT_SQLITE_SCHEMA_VERSION
from iris.core.datetime_utils import now_utc

if TYPE_CHECKING:
    from collections.abc import Iterable

    from iris.adapters.persistence.sqlite.migrator_types import SQLiteMigration


class SQLiteMigrationStatus(StrEnum):
    """Migration runner の実行結果。"""

    INITIALIZED = "initialized"
    UPGRADED = "upgraded"
    ALREADY_CURRENT = "already_current"


@dataclass(frozen=True)
class SQLiteSchemaStatus:
    """SQLite schema の read-only 診断結果。"""

    db_path: Path
    exists: bool
    user_version: int | None
    current_version: int
    latest_migration: str | None
    latest_migration_version: int | None
    pending_versions: tuple[int, ...]
    quick_check: str | None
    wal_checkpoint: str | None


@dataclass(frozen=True)
class SQLiteMigrationResult:
    """SQLite migration runner の実行結果。"""

    db_path: Path
    previous_version: int
    current_version: int
    status: SQLiteMigrationStatus
    applied_versions: tuple[int, ...]


class SQLiteSchemaError(RuntimeError):
    """SQLite schema 管理に関する基底例外。"""


class SQLiteMigrationError(SQLiteSchemaError):
    """Migration 適用失敗。"""


class SQLiteUnsupportedSchemaVersionError(SQLiteSchemaError):
    """現在の runtime が扱えない future schema version。"""


class SQLiteCorruptDatabaseError(SQLiteSchemaError):
    """SQLite DB が unreadable または corrupt。"""


class SQLiteLegacySchemaError(SQLiteSchemaError):
    """既存 unversioned schema が baseline と互換でない。"""


class SQLiteMigrationHistoryError(SQLiteSchemaError):
    """migration history が current migration 定義と一致しない。"""


_REQUIRED_COLUMNS: dict[str, frozenset[str]] = {
    "schema_migrations": frozenset({"version", "name", "checksum", "applied_at"}),
    "accounts": frozenset(
        {
            "account_id",
            "provider",
            "provider_subject",
            "display_name",
            "linked_actor_id",
            "metadata_json",
        }
    ),
    "memories": frozenset(
        {
            "memory_id",
            "text",
            "actor_id",
            "space_id",
            "salience",
            "kind",
            "confidence",
            "source_observation_id",
            "created_at",
            "updated_at",
            "archived",
            "metadata_json",
        }
    ),
    "memories_fts5": frozenset({"text", "memory_id"}),
    "relationship_snapshots": frozenset(
        {
            "actor_id",
            "actor_label",
            "affinity",
            "trust",
            "familiarity",
            "relationship_summary",
            "source_observation_id",
            "created_at",
            "updated_at",
            "version",
        }
    ),
    "affect_baselines": frozenset(
        {
            "owner_key",
            "scope",
            "actor_id",
            "mood_label",
            "valence",
            "arousal",
            "dominance",
            "affect_summary",
            "source_observation_id",
            "created_at",
            "updated_at",
            "version",
        }
    ),
    "activity_events": frozenset(
        {
            "activity_id",
            "source",
            "provider_event_id",
            "actor_id",
            "space_id",
            "activity_kind",
            "occurred_at",
            "received_at",
            "payload_json",
        }
    ),
    "delivery_outbox": frozenset(
        {
            "delivery_id",
            "idempotency_key",
            "status",
            "created_at",
            "updated_at",
            "not_before",
            "attempts",
            "max_attempts",
            "lease_id",
            "lease_expires_at",
            "blocked_reason",
            "last_error_reason",
            "source_observation_id",
            "target_provider",
            "target_provider_subject",
            "target_provider_space_ref",
            "target_session_id",
            "target_actor_id",
            "target_account_id",
            "target_space_id",
            "action_type",
            "action_id",
            "action_session_id",
            "action_correlation_id",
            "action_text",
        }
    ),
    "delivery_report_fingerprints": frozenset(
        {
            "fingerprint_key",
            "delivery_id",
            "lease_id",
            "action_id",
            "correlation_id",
            "status",
            "external_message_id",
            "error_reason",
        }
    ),
    "scheduler_targets": frozenset(
        {
            "provider",
            "provider_subject",
            "provider_space_ref",
            "session_id",
            "actor_id",
            "account_id",
            "space_id",
            "display_name",
            "last_observed_at",
            "last_scheduler_attempt_at",
            "stale_after",
            "route_display_name",
        }
    ),
    "background_jobs": BACKGROUND_JOB_REQUIRED_COLUMNS,
    "memory_candidate_reviews": MEMORY_CANDIDATE_REVIEW_REQUIRED_COLUMNS,
    "conversation_transcripts": CONVERSATION_TRANSCRIPT_REQUIRED_COLUMNS,
}


class SQLiteSchemaMigrator:
    """SQLite backend startup 用 migration runner。"""

    def __init__(self, migrations: Iterable[SQLiteMigration] | None = None) -> None:
        """Migration runner を初期化する。

        Args:
            migrations: テスト用に差し替え可能な migration 群。省略時は本番 migration。
        """
        if migrations is None:
            migrations = available_migrations()
        self._migrations = tuple(sorted(migrations, key=lambda migration: migration.version))

    def inspect(self, db_path: str | Path) -> SQLiteSchemaStatus:
        """DB を変更せずに schema 状態を読む。

        Returns:
            SQLiteSchemaStatus: DB の schema 診断結果。

        Raises:
            SQLiteCorruptDatabaseError: DB が unreadable または corrupt の場合。
        """
        path = Path(db_path)
        if not path.exists():
            return _missing_status(path, self._migration_versions())
        if path.is_dir():
            message = f"SQLite DB path is a directory: {path}"
            raise SQLiteCorruptDatabaseError(message)
        try:
            with contextlib.closing(_connect(path)) as conn:
                return self._inspect_connection(path, conn)
        except sqlite3.DatabaseError as exc:
            message = _corrupt_message(path, str(exc))
            raise SQLiteCorruptDatabaseError(message) from exc

    def ensure_current(self, db_path: str | Path) -> SQLiteMigrationResult:
        """DB を current schema version へ migration する。

        Returns:
            SQLiteMigrationResult: 適用した migration と到達 version。

        Raises:
            SQLiteCorruptDatabaseError: DB が unreadable または corrupt の場合。
        """
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with contextlib.closing(_connect(path)) as conn:
                return self._ensure_current_connection(path, conn)
        except sqlite3.DatabaseError as exc:
            message = _corrupt_message(path, str(exc))
            raise SQLiteCorruptDatabaseError(message) from exc

    def _ensure_current_connection(
        self,
        path: Path,
        conn: sqlite3.Connection,
    ) -> SQLiteMigrationResult:
        _assert_quick_check(path, conn)
        previous_version = _user_version(conn)
        _assert_supported_version(path, previous_version)
        if previous_version == CURRENT_SQLITE_SCHEMA_VERSION:
            _validate_current_schema(path, conn)
            self._validate_migration_history(path, conn, previous_version)
            return SQLiteMigrationResult(
                db_path=path,
                previous_version=previous_version,
                current_version=previous_version,
                status=SQLiteMigrationStatus.ALREADY_CURRENT,
                applied_versions=(),
            )
        if previous_version == 0:
            _validate_unversioned_adoption(path, conn)
        applied = self._apply_pending(path, conn, previous_version)
        _validate_current_schema(path, conn)
        self._validate_migration_history(path, conn, CURRENT_SQLITE_SCHEMA_VERSION)
        return SQLiteMigrationResult(
            db_path=path,
            previous_version=previous_version,
            current_version=CURRENT_SQLITE_SCHEMA_VERSION,
            status=_migration_status(previous_version),
            applied_versions=applied,
        )

    def _apply_pending(
        self,
        path: Path,
        conn: sqlite3.Connection,
        current_version: int,
    ) -> tuple[int, ...]:
        pending = tuple(m for m in self._migrations if m.version > current_version)
        for migration in pending:
            self._apply_one(path, conn, migration)
        return tuple(m.version for m in pending)

    @staticmethod
    def _apply_one(
        path: Path,
        conn: sqlite3.Connection,
        migration: SQLiteMigration,
    ) -> None:
        try:
            conn.execute("BEGIN IMMEDIATE")
            for statement in migration.statements:
                conn.execute(statement)
            _record_migration(conn, migration)
            conn.execute(f"PRAGMA user_version = {migration.version}")
            conn.commit()
        except sqlite3.DatabaseError as exc:
            _rollback(conn)
            message = f"failed to apply SQLite migration v{migration.version} to {path}: {exc}"
            raise SQLiteMigrationError(message) from exc

    def _inspect_connection(self, path: Path, conn: sqlite3.Connection) -> SQLiteSchemaStatus:
        quick = _quick_check(conn)
        if quick != "ok":
            raise SQLiteCorruptDatabaseError(_corrupt_message(path, quick))
        version = _user_version(conn)
        _assert_supported_version(path, version)
        if version == CURRENT_SQLITE_SCHEMA_VERSION:
            _validate_current_schema(path, conn)
            self._validate_migration_history(path, conn, version)
        latest = _latest_migration(conn)
        return SQLiteSchemaStatus(
            db_path=path,
            exists=True,
            user_version=version,
            current_version=CURRENT_SQLITE_SCHEMA_VERSION,
            latest_migration=latest.name,
            latest_migration_version=latest.version,
            pending_versions=_pending_versions(version, self._migration_versions()),
            quick_check=quick,
            wal_checkpoint=_wal_checkpoint_status(conn),
        )

    def _validate_migration_history(
        self,
        path: Path,
        conn: sqlite3.Connection,
        version: int,
    ) -> None:
        expected = {migration.version: migration for migration in self._migrations}
        missing: list[str] = []
        mismatched: list[str] = []
        for migration_version in range(1, version + 1):
            migration = expected.get(migration_version)
            if migration is None:
                missing.append(str(migration_version))
                continue
            row = conn.execute(
                """
                SELECT name, checksum
                FROM schema_migrations
                WHERE version = ?
                """,
                (migration_version,),
            ).fetchone()
            if row is None:
                missing.append(str(migration_version))
                continue
            if str(row["name"]) != migration.name or str(row["checksum"]) != migration.checksum:
                mismatched.append(str(migration_version))
        if missing or mismatched:
            details: list[str] = []
            if missing:
                details.append(f"missing versions: {','.join(missing)}")
            if mismatched:
                details.append(f"checksum/name mismatch: {','.join(mismatched)}")
            message = f"SQLite migration history at {path} is not trusted: {'; '.join(details)}"
            raise SQLiteMigrationHistoryError(message)

    def _migration_versions(self) -> tuple[int, ...]:
        return tuple(migration.version for migration in self._migrations)


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _user_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    if row is None:
        return 0
    return int(row[0])


def _assert_supported_version(path: Path, version: int) -> None:
    if version <= CURRENT_SQLITE_SCHEMA_VERSION:
        return
    message = (
        f"SQLite schema version {version} at {path} is newer than supported "
        f"version {CURRENT_SQLITE_SCHEMA_VERSION}; upgrade Iris before opening this DB."
    )
    raise SQLiteUnsupportedSchemaVersionError(message)


def _assert_quick_check(path: Path, conn: sqlite3.Connection) -> None:
    result = _quick_check(conn)
    if result != "ok":
        raise SQLiteCorruptDatabaseError(_corrupt_message(path, result))


def _quick_check(conn: sqlite3.Connection) -> str:
    row = conn.execute("PRAGMA quick_check").fetchone()
    if row is None:
        return "quick_check returned no rows"
    return str(row[0])


@dataclass(frozen=True)
class _LatestMigration:
    version: int | None
    name: str | None


def _latest_migration(conn: sqlite3.Connection) -> _LatestMigration:
    if not _table_exists(conn, "schema_migrations"):
        return _LatestMigration(version=None, name=None)
    row = conn.execute(
        """
        SELECT version, name
        FROM schema_migrations
        ORDER BY version DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return _LatestMigration(version=None, name=None)
    return _LatestMigration(version=int(row["version"]), name=str(row["name"]))


def _record_migration(conn: sqlite3.Connection, migration: SQLiteMigration) -> None:
    conn.execute(
        """
        INSERT INTO schema_migrations(version, name, checksum, applied_at)
        VALUES (?, ?, ?, ?)
        """,
        (migration.version, migration.name, migration.checksum, now_utc().isoformat()),
    )


def _validate_unversioned_adoption(path: Path, conn: sqlite3.Connection) -> None:
    missing: list[str] = []
    for table_name, required_columns in _REQUIRED_COLUMNS.items():
        if table_name == "schema_migrations" or not _table_exists(conn, table_name):
            continue
        existing = _table_columns(conn, table_name)
        missing.extend(f"{table_name}.{name}" for name in required_columns - existing)
    if missing:
        details = ", ".join(sorted(missing))
        message = f"SQLite unversioned schema at {path} is not safely adoptable: {details}"
        raise SQLiteLegacySchemaError(message)


def _validate_current_schema(path: Path, conn: sqlite3.Connection) -> None:
    missing: list[str] = []
    for table_name, required_columns in _REQUIRED_COLUMNS.items():
        missing.extend(_missing_columns(conn, table_name, required_columns))
    if missing:
        details = ", ".join(sorted(missing))
        message = f"SQLite schema at {path} is not compatible with current SQLite schema: {details}"
        raise SQLiteLegacySchemaError(message)


def _missing_columns(
    conn: sqlite3.Connection,
    table_name: str,
    required_columns: frozenset[str],
) -> tuple[str, ...]:
    if not _table_exists(conn, table_name):
        return (f"{table_name}.*",)
    existing = _table_columns(conn, table_name)
    return tuple(f"{table_name}.{name}" for name in required_columns - existing)


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE name = ? AND type IN ('table', 'view')
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> frozenset[str]:
    rows = conn.execute("SELECT name FROM pragma_table_info(?)", (table_name,)).fetchall()
    return frozenset(str(row["name"]) for row in rows)


def _migration_status(previous_version: int) -> SQLiteMigrationStatus:
    if previous_version == 0:
        return SQLiteMigrationStatus.INITIALIZED
    return SQLiteMigrationStatus.UPGRADED


def _pending_versions(user_version: int, migration_versions: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(version for version in migration_versions if version > user_version)


def _wal_checkpoint_status(conn: sqlite3.Connection) -> str:
    row = conn.execute("PRAGMA journal_mode").fetchone()
    if row is None:
        return "unknown"
    return f"journal_mode={row[0]}"


def _missing_status(path: Path, migration_versions: tuple[int, ...]) -> SQLiteSchemaStatus:
    return SQLiteSchemaStatus(
        db_path=path,
        exists=False,
        user_version=None,
        current_version=CURRENT_SQLITE_SCHEMA_VERSION,
        latest_migration=None,
        latest_migration_version=None,
        pending_versions=migration_versions,
        quick_check=None,
        wal_checkpoint=None,
    )


def _rollback(conn: sqlite3.Connection) -> None:
    if conn.in_transaction:
        conn.rollback()


def _corrupt_message(path: Path, reason: str) -> str:
    return (
        f"SQLite DB at {path} is unreadable or corrupt: {reason}. "
        "Original DB was left untouched. Restore from a verified backup before retrying."
    )
