"""Shared SQLite database foundation for adapters."""

from __future__ import annotations

import contextlib
from pathlib import Path
import sqlite3
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator


class SQLiteDatabase:
    """Shared SQLite database lifecycle and transaction manager.

    This is not an ORM or global registry. It only centralizes low-level
    connection boilerplate, busy_timeout pragmas, and thread-safe read/write
    transaction acquisition.
    """

    def __init__(
        self,
        db_path: str | Path,
        *,
        timeout: float = 5.0,
        busy_timeout_ms: int = 5000,
        journal_mode: str | None = None,
        synchronous: str | None = None,
    ) -> None:
        """Initialize the database connection.

        Args:
            db_path: Path to the SQLite database file.
            timeout: Connection timeout in seconds.
            busy_timeout_ms: PRAGMA busy_timeout in milliseconds.
            journal_mode: Optional PRAGMA journal_mode (e.g. "WAL").
            synchronous: Optional PRAGMA synchronous (e.g. "NORMAL").
        """
        self._db_path = Path(db_path)
        self._write_lock = threading.Lock()
        self._conn_lock = threading.RLock()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._timeout = timeout
        self._busy_timeout_ms = busy_timeout_ms
        self._journal_mode = journal_mode
        self._synchronous = synchronous

        self._conn = self._connect()

    def _connect(self) -> sqlite3.Connection:
        """Create and configure a new sqlite3 connection.

        Returns:
            sqlite3.Connection: The new connection.
        """
        conn = sqlite3.connect(self._db_path, timeout=self._timeout, check_same_thread=False)
        conn.row_factory = sqlite3.Row

        # Essential pragmas for concurrent reliability
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms};")

        if self._journal_mode:
            conn.execute(f"PRAGMA journal_mode = {self._journal_mode};")
        if self._synchronous:
            conn.execute(f"PRAGMA synchronous = {self._synchronous};")

        return conn

    @property
    def write_lock(self) -> threading.Lock:
        """Get the global write lock for this database instance."""
        return self._write_lock

    @contextlib.contextmanager
    def transaction(self, *, immediate: bool = False) -> Generator[sqlite3.Connection]:
        """Provide a thread-safe transactional connection.

        Args:
            immediate: If True, uses 'BEGIN IMMEDIATE' to acquire the write lock
                immediately, avoiding SQLITE_BUSY during read-modify-write.

        Yields:
            sqlite3.Connection: The managed connection.
        """
        with self._conn_lock:
            if immediate:
                txn_active = False
                try:
                    self._conn.execute("BEGIN IMMEDIATE")
                    txn_active = True
                    yield self._conn
                    self._conn.commit()
                except Exception:
                    if txn_active:
                        with contextlib.suppress(sqlite3.OperationalError):
                            self._conn.execute("ROLLBACK")
                    raise
            else:
                with self._conn:
                    yield self._conn

    def close(self) -> None:
        """Close the underlying connection safely."""
        with self._conn_lock:
            self._conn.close()

    def __del__(self) -> None:
        """Ensure connection is closed on deletion."""
        if hasattr(self, "_conn"):
            with contextlib.suppress(sqlite3.ProgrammingError, TypeError, AttributeError):
                self.close()
