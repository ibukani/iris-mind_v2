"""SQLite persistence context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.adapters.persistence.sqlite.engine import AsyncDatabaseManager


@dataclass(frozen=True)
class SQLitePersistenceContext:
    """Shared SQLite persistence context for stores."""

    db: AsyncDatabaseManager

    async def close(self) -> None:
        """Close the underlying database engine."""
        await self.db.close()
