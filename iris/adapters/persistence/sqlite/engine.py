"""Async SQLAlchemy engine initialization."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import Connection, event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from iris.adapters.persistence.sqlite.migrator import SQLiteSchemaMigrator

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession


class AsyncDatabaseManager:
    """Manages the lifecycle of an async SQLAlchemy engine."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        echo: bool = False,
        ensure_schema: bool = True,
        migrator: SQLiteSchemaMigrator | None = None,
    ) -> None:
        """Initialize the async engine.

        Args:
            db_path: Path to the SQLite database file.
            echo: If True, echo SQL queries for debugging.
            ensure_schema: True の場合、engine 使用前に SQLite schema migration を実行する。
            migrator: schema migration に使う runner。省略時は標準 runner。
        """
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        # Connect string for aiosqlite
        # Example: sqlite+aiosqlite:///path/to/database.db
        connect_str = f"sqlite+aiosqlite:///{self._db_path.absolute()}"

        self._transaction_lock = asyncio.Lock()
        self.engine: AsyncEngine = create_async_engine(
            connect_str,
            echo=echo,
        )

        def do_begin(conn: Connection) -> None:
            conn.exec_driver_sql("BEGIN IMMEDIATE")

        event.listen(self.engine.sync_engine, "begin", do_begin)

        if ensure_schema:
            (migrator or SQLiteSchemaMigrator()).ensure_current(self._db_path)

        self.session_factory = async_sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )

    @property
    def db_path(self) -> Path:
        """管理対象 SQLite DB path を返す。"""
        return self._db_path

    async def close(self) -> None:
        """Close the engine."""
        await self.engine.dispose()

    @contextlib.asynccontextmanager
    async def transaction(self) -> AsyncGenerator[AsyncSession]:
        """Provide a transactional async session.

        The session automatically commits on success and rolls back on error.

        Yields:
            AsyncSession: The database session.
        """
        async with self._transaction_lock, self.session_factory() as session, session.begin():
            yield session
