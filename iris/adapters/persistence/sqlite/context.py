"""SQLite persistence context."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from iris.adapters.persistence.sqlite.engine import AsyncDatabaseManager


@dataclass(frozen=True)
class SQLitePersistenceContext:
    """Shared SQLite persistence context for stores."""

    db: AsyncDatabaseManager

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
