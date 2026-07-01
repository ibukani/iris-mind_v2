"""SQLite backup / restore tests。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from iris.adapters.persistence.sqlite.backup import (
    BACKUP_DB_FILENAME,
    BACKUP_MANIFEST_FILENAME,
    SQLiteBackupError,
    SQLiteBackupService,
    read_backup_manifest,
)
from iris.adapters.persistence.sqlite.schema.version import CURRENT_SQLITE_SCHEMA_VERSION
from iris.adapters.persistence.sqlite.stores.memory import SQLiteMemoryStore
from iris.contracts.memory import MemoryId, MemoryRecord

if TYPE_CHECKING:
    from pathlib import Path


def test_sqlite_backup_creates_metadata_and_restorable_snapshot(tmp_path: Path) -> None:
    """Backup は manifest 付き artifact を作り、restore 後に store から読める。"""
    source_db = tmp_path / "source.sqlite3"
    store = SQLiteMemoryStore(source_db)
    store.put(MemoryRecord(id=MemoryId("m1"), text="backup tea memory"))
    store.close()

    backup_dir = tmp_path / "backup"
    manifest = SQLiteBackupService().create_backup(source_db, backup_dir)

    assert manifest.format_version == 1
    assert manifest.schema_version == CURRENT_SQLITE_SCHEMA_VERSION
    assert manifest.backup_db_filename == BACKUP_DB_FILENAME
    assert (backup_dir / BACKUP_DB_FILENAME).exists()
    assert (backup_dir / BACKUP_MANIFEST_FILENAME).exists()
    loaded = read_backup_manifest(backup_dir / BACKUP_MANIFEST_FILENAME)
    assert loaded.sqlite_checksum_sha256 == manifest.sqlite_checksum_sha256

    restored_db = tmp_path / "restored.sqlite3"
    restored_manifest = SQLiteBackupService().restore_backup(backup_dir, restored_db)
    restored_store = SQLiteMemoryStore(restored_db)
    restored = restored_store.get(MemoryId("m1"))

    assert restored_manifest == manifest
    assert restored is not None
    assert restored.text == "backup tea memory"
    restored_store.close()


def test_sqlite_restore_rejects_checksum_mismatch(tmp_path: Path) -> None:
    """Manifest checksum と DB 内容が異なる backup は restore しない。"""
    source_db = tmp_path / "source.sqlite3"
    store = SQLiteMemoryStore(source_db)
    store.put(MemoryRecord(id=MemoryId("m1"), text="checksum memory"))
    store.close()
    backup_dir = tmp_path / "backup"
    SQLiteBackupService().create_backup(source_db, backup_dir)
    with (backup_dir / BACKUP_DB_FILENAME).open("ab") as handle:
        handle.write(b"mutated")

    with pytest.raises(SQLiteBackupError, match="checksum mismatch"):
        SQLiteBackupService().restore_backup(backup_dir, tmp_path / "target.sqlite3")


def test_sqlite_restore_requires_explicit_overwrite(tmp_path: Path) -> None:
    """既存 target DB は overwrite=True なしでは上書きしない。"""
    source_db = tmp_path / "source.sqlite3"
    SQLiteMemoryStore(source_db).close()
    backup_dir = tmp_path / "backup"
    SQLiteBackupService().create_backup(source_db, backup_dir)
    target_db = tmp_path / "target.sqlite3"
    SQLiteMemoryStore(target_db).close()

    with pytest.raises(SQLiteBackupError, match="already exists"):
        SQLiteBackupService().restore_backup(backup_dir, target_db)

    SQLiteBackupService().restore_backup(backup_dir, target_db, overwrite=True)


def test_sqlite_restore_rejects_target_with_wal_sidecar(tmp_path: Path) -> None:
    """WAL/SHM sidecar が残る target への restore は offline 前提違反として拒否する。"""
    source_db = tmp_path / "source.sqlite3"
    SQLiteMemoryStore(source_db).close()
    backup_dir = tmp_path / "backup"
    SQLiteBackupService().create_backup(source_db, backup_dir)
    target_db = tmp_path / "target.sqlite3"
    SQLiteMemoryStore(target_db).close()
    target_db.with_name(f"{target_db.name}-wal").write_bytes(b"pending wal")

    with pytest.raises(SQLiteBackupError, match="offline checkpointed target"):
        SQLiteBackupService().restore_backup(backup_dir, target_db, overwrite=True)
