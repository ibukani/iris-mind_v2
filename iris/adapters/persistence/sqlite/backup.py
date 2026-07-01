"""SQLite backup / restore service。"""

from __future__ import annotations

import contextlib
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

from pydantic import BaseModel, ConfigDict, ValidationError

from iris.adapters.persistence.sqlite.migrator import SQLiteSchemaMigrator
from iris.core.datetime_utils import now_utc

BACKUP_FORMAT_VERSION = 1
BACKUP_DB_FILENAME = "state.sqlite3"
BACKUP_MANIFEST_FILENAME = "manifest.json"


class _SQLiteBackupManifestPayload(BaseModel):
    """Manifest JSON payload validation model。"""

    model_config = ConfigDict(extra="forbid")

    format_version: int
    schema_version: int
    created_at: str
    source_db_path: str
    sqlite_checksum_sha256: str
    backup_db_filename: str
    app_version: str | None = None


@dataclass(frozen=True)
class SQLiteBackupManifest:
    """SQLite backup artifact metadata。"""

    format_version: int
    schema_version: int
    created_at: str
    source_db_path: str
    sqlite_checksum_sha256: str
    backup_db_filename: str
    app_version: str | None = None


class SQLiteBackupError(RuntimeError):
    """SQLite backup / restore 失敗。"""


class SQLiteBackupService:
    """SQLite online backup API を使う backup / restore service。"""

    def __init__(self, migrator: SQLiteSchemaMigrator | None = None) -> None:
        """Service を初期化する。"""
        self._migrator = migrator or SQLiteSchemaMigrator()

    def create_backup(self, source_db: str | Path, backup_dir: str | Path) -> SQLiteBackupManifest:
        """SQLite DB 全体の restorable backup artifact を作成する。

        Returns:
            SQLiteBackupManifest: 作成した backup manifest。
        """
        source_path = Path(source_db)
        target_dir = Path(backup_dir)
        backup_path = target_dir / BACKUP_DB_FILENAME
        manifest_path = target_dir / BACKUP_MANIFEST_FILENAME
        _validate_source(source_path)
        _validate_backup_target(backup_path, manifest_path)

        self._migrator.ensure_current(source_path)
        target_dir.mkdir(parents=True, exist_ok=True)
        _copy_with_online_backup(source_path, backup_path)
        manifest = self._build_manifest(source_path, backup_path)
        manifest_path.write_text(_manifest_json(manifest), encoding="utf-8")
        return manifest

    def restore_backup(
        self,
        backup_dir: str | Path,
        target_db: str | Path,
        *,
        overwrite: bool = False,
    ) -> SQLiteBackupManifest:
        """Backup artifact を offline target DB へ復元する。

        既存 DB を上書きする restore は、Iris と他 process が DB を閉じ、
        WAL / SHM sidecar が残っていない checkpoint 済み状態でのみ許可する。

        Returns:
            SQLiteBackupManifest: 復元に使った backup manifest。
        """
        source_dir = Path(backup_dir)
        backup_path = source_dir / BACKUP_DB_FILENAME
        manifest = read_backup_manifest(source_dir / BACKUP_MANIFEST_FILENAME)
        _validate_backup_payload(backup_path, manifest)
        _validate_restore_target(Path(target_db), overwrite=overwrite)
        self._migrator.inspect(backup_path)

        target_path = Path(target_db)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        _replace_target_db(backup_path, target_path)
        self._migrator.inspect(target_path)
        return manifest

    def _build_manifest(self, source_path: Path, backup_path: Path) -> SQLiteBackupManifest:
        status = self._migrator.inspect(backup_path)
        schema_version = status.user_version or 0
        return SQLiteBackupManifest(
            format_version=BACKUP_FORMAT_VERSION,
            schema_version=schema_version,
            created_at=now_utc().isoformat(),
            source_db_path=str(source_path),
            sqlite_checksum_sha256=sha256_file(backup_path),
            backup_db_filename=BACKUP_DB_FILENAME,
        )


def read_backup_manifest(manifest_path: str | Path) -> SQLiteBackupManifest:
    """Manifest JSON を検証して読み込む。

    Returns:
        SQLiteBackupManifest: 検証済み manifest。

    Raises:
        SQLiteBackupError: manifest が存在しない、または形式不正の場合。
    """
    path = Path(manifest_path)
    if not path.exists():
        message = f"backup manifest not found: {path}"
        raise SQLiteBackupError(message)
    try:
        payload = _SQLiteBackupManifestPayload.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        message = f"backup manifest is invalid: {path}"
        raise SQLiteBackupError(message) from exc
    return SQLiteBackupManifest(
        format_version=payload.format_version,
        schema_version=payload.schema_version,
        created_at=payload.created_at,
        source_db_path=payload.source_db_path,
        sqlite_checksum_sha256=payload.sqlite_checksum_sha256,
        backup_db_filename=payload.backup_db_filename,
        app_version=payload.app_version,
    )


def sha256_file(path: str | Path) -> str:
    """File 内容の SHA-256 checksum を返す。

    Returns:
        str: hex encoded SHA-256 checksum。
    """
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_with_online_backup(source_path: Path, backup_path: Path) -> None:
    source_uri = f"file:{source_path}?mode=ro"
    with (
        contextlib.closing(sqlite3.connect(source_uri, uri=True)) as source,
        contextlib.closing(sqlite3.connect(backup_path)) as target,
    ):
        source.backup(target)


def _validate_source(source_path: Path) -> None:
    if not source_path.exists():
        message = f"source SQLite DB not found: {source_path}"
        raise SQLiteBackupError(message)
    if source_path.is_dir():
        message = f"source SQLite DB path is a directory: {source_path}"
        raise SQLiteBackupError(message)


def _validate_backup_target(backup_path: Path, manifest_path: Path) -> None:
    if backup_path.exists() or manifest_path.exists():
        message = f"backup artifact already exists under: {backup_path.parent}"
        raise SQLiteBackupError(message)


def _validate_backup_payload(backup_path: Path, manifest: SQLiteBackupManifest) -> None:
    if not backup_path.exists():
        message = f"backup SQLite DB not found: {backup_path}"
        raise SQLiteBackupError(message)
    if manifest.format_version != BACKUP_FORMAT_VERSION:
        message = f"unsupported backup format version: {manifest.format_version}"
        raise SQLiteBackupError(message)
    if manifest.backup_db_filename != BACKUP_DB_FILENAME:
        message = f"unexpected backup DB filename: {manifest.backup_db_filename}"
        raise SQLiteBackupError(message)
    checksum = sha256_file(backup_path)
    if checksum != manifest.sqlite_checksum_sha256:
        message = "backup checksum mismatch"
        raise SQLiteBackupError(message)


def _validate_restore_target(target_path: Path, *, overwrite: bool) -> None:
    if target_path.exists() and not overwrite:
        message = f"target SQLite DB already exists: {target_path}"
        raise SQLiteBackupError(message)
    if target_path.is_dir():
        message = f"target SQLite DB path is a directory: {target_path}"
        raise SQLiteBackupError(message)
    sidecars = _existing_sqlite_sidecars(target_path)
    if sidecars:
        files = ", ".join(str(path) for path in sidecars)
        message = (
            "target SQLite DB has WAL/SHM sidecar files; restore requires an offline "
            f"checkpointed target before overwrite: {files}"
        )
        raise SQLiteBackupError(message)


def _existing_sqlite_sidecars(target_path: Path) -> tuple[Path, ...]:
    return tuple(
        sidecar
        for sidecar in (
            target_path.with_name(f"{target_path.name}-wal"),
            target_path.with_name(f"{target_path.name}-shm"),
        )
        if sidecar.exists()
    )


def _replace_target_db(backup_path: Path, target_path: Path) -> None:
    temporary_path = target_path.with_name(f"{target_path.name}.restore.tmp")
    try:
        shutil.copy2(backup_path, temporary_path)
        temporary_path.replace(target_path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary_path.unlink()


def _manifest_json(manifest: SQLiteBackupManifest) -> str:
    return json.dumps(asdict(manifest), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
