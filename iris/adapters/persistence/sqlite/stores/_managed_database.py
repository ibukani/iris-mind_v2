"""Schema 管理を伴う SQLite store の共通 lifecycle。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.adapters.persistence.sqlite.database import SQLiteDatabase
from iris.adapters.persistence.sqlite.migrator import SQLiteSchemaMigrator

if TYPE_CHECKING:
    from pathlib import Path


class ManagedSQLiteStore:
    """Migration と connection close を共有する SQLite store 基底。"""

    def __init__(
        self,
        db_path: str | Path,
        *,
        ensure_schema: bool = True,
        migrator: SQLiteSchemaMigrator | None = None,
    ) -> None:
        """Migration 済み SQLite DB に接続する。"""
        if ensure_schema:
            (migrator or SQLiteSchemaMigrator()).ensure_current(db_path)
        self._db = SQLiteDatabase(db_path, synchronous="NORMAL")

    def close(self) -> None:
        """永続 connection を閉じる。"""
        self._db.close()
