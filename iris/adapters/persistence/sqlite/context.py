"""SQLite persistence context."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Self

from iris.adapters.persistence.sqlite.engine import AsyncDatabaseManager
from iris.adapters.persistence.sqlite.migrator import SQLiteSchemaMigrator


@dataclass(frozen=True)
class SQLitePersistenceContext:
    """SQLite schema migration 済み database manager の共有 context。"""

    db: AsyncDatabaseManager
    schema_is_current: bool = True

    @classmethod
    def open(
        cls,
        db_path: str | Path,
        *,
        echo: bool = False,
        migrator: SQLiteSchemaMigrator | None = None,
    ) -> Self:
        """Schema migration を一度だけ実行して context を開く。

        Returns:
            SQLitePersistenceContext: migration 済み DB manager を持つ context。
        """
        runner = migrator or SQLiteSchemaMigrator()
        runner.ensure_current(db_path)
        return cls(
            db=AsyncDatabaseManager(
                db_path,
                echo=echo,
                ensure_schema=False,
                migrator=runner,
            ),
            schema_is_current=True,
        )

    @property
    def db_path(self) -> Path:
        """Context が管理する SQLite DB path を返す。"""
        return self.db.db_path

    async def close(self) -> None:
        """Close the underlying database engine."""
        await self.db.close()


type SQLiteDatabaseInput = str | Path | AsyncDatabaseManager | SQLitePersistenceContext


def resolve_database_manager(db: SQLiteDatabaseInput) -> AsyncDatabaseManager:
    """Store constructor入力を共有database managerへ正規化する。

    Returns:
        既存または新規作成したdatabase manager。
    """
    if isinstance(db, SQLitePersistenceContext):
        return db.db
    if isinstance(db, AsyncDatabaseManager):
        return db
    return AsyncDatabaseManager(db)
