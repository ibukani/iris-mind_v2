"""SQLite account store implementation."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
import sqlite3
from typing import TYPE_CHECKING, override

from iris.adapters.app_gateway.ports import AccountStore
from iris.contracts.accounts import AccountProfile, AccountStoreError
from iris.core.ids import AccountId, ActorId, ExternalRef

if TYPE_CHECKING:
    from collections.abc import Generator


class SQLiteAccountStore(AccountStore):
    """SQLite-backed account store.

    Note: This is a simple/local adapter that executes synchronous sqlite3 I/O
    directly. Long-term, this could be migrated to aiosqlite or asyncio.to_thread
    if event loop blocking becomes a concern under high concurrent load.
    """

    def __init__(self, db_path: str | Path) -> None:
        """Initialize the store and create tables if missing."""
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Create the accounts table if it does not exist."""
        query = """
        CREATE TABLE IF NOT EXISTS accounts (
            account_id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            provider_subject TEXT NOT NULL,
            display_name TEXT NOT NULL,
            linked_actor_id TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(provider, provider_subject)
        );
        """
        with self._transaction() as conn:
            conn.execute(query)

    def _connect(self) -> sqlite3.Connection:
        """Get a configured sqlite3 connection.

        Returns:
            sqlite3.Connection: A new configured connection.
        """
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    @contextlib.contextmanager
    def _transaction(self) -> Generator[sqlite3.Connection]:
        """Provide a transactional sqlite connection that closes when done.

        Yields:
            sqlite3.Connection: An open, managed connection.
        """
        with contextlib.closing(self._connect()) as conn, conn:
            yield conn

    @staticmethod
    def _row_to_profile(row: sqlite3.Row) -> AccountProfile:
        """Convert a database row to an AccountProfile.

        Returns:
            AccountProfile: The mapped account profile.
        """
        linked = row["linked_actor_id"]
        return AccountProfile(
            account_id=AccountId(row["account_id"]),
            provider=row["provider"],
            provider_subject=ExternalRef(row["provider_subject"]),
            display_name=row["display_name"],
            linked_actor_id=ActorId(linked) if linked else None,
            metadata=json.loads(row["metadata_json"]),
        )

    @override
    async def get_by_external_ref(
        self,
        *,
        provider: str,
        provider_subject: ExternalRef,
    ) -> AccountProfile | None:
        """Get an account profile by provider and subject.

        Returns:
            AccountProfile | None: The found account profile, or None.
        """
        query = "SELECT * FROM accounts WHERE provider = ? AND provider_subject = ?"
        with self._transaction() as conn:
            cursor = conn.execute(query, (provider, str(provider_subject)))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_profile(row)

    @override
    async def get_by_account_id(
        self,
        account_id: AccountId,
    ) -> AccountProfile | None:
        """Get an account profile by its internal AccountId.

        Returns:
            AccountProfile | None: The found account profile, or None.
        """
        query = "SELECT * FROM accounts WHERE account_id = ?"
        with self._transaction() as conn:
            cursor = conn.execute(query, (str(account_id),))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_profile(row)

    @override
    async def put(
        self,
        account: AccountProfile,
    ) -> AccountProfile:
        """Create or update an account profile.

        Returns:
            AccountProfile: The inserted or updated account profile.

        Raises:
            AccountStoreError: On duplicate account ID with different refs,
                or duplicate ref with different account ID.
        """
        with self._transaction() as conn:
            # Check for existing by account_id
            cursor = conn.execute(
                "SELECT provider, provider_subject FROM accounts WHERE account_id = ?",
                (str(account.account_id),),
            )
            existing_by_id = cursor.fetchone()
            if existing_by_id and (
                existing_by_id["provider"] != account.provider
                or existing_by_id["provider_subject"] != account.provider_subject
            ):
                msg = "account_id conflict: already exists with different external refs"
                raise AccountStoreError(msg)

            # Check for existing by external ref
            cursor = conn.execute(
                "SELECT account_id FROM accounts WHERE provider = ? AND provider_subject = ?",
                (account.provider, str(account.provider_subject)),
            )
            existing_by_ref = cursor.fetchone()
            if existing_by_ref and existing_by_ref["account_id"] != account.account_id:
                msg = "external ref conflict: already exists with different account_id"
                raise AccountStoreError(msg)

            # Insert or update
            metadata_json = json.dumps(dict(account.metadata))
            linked_id = str(account.linked_actor_id) if account.linked_actor_id else None

            # SQLite UPSERT
            query = """
            INSERT INTO accounts (
                account_id, provider, provider_subject, display_name,
                linked_actor_id, metadata_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(account_id) DO UPDATE SET
                display_name=excluded.display_name,
                linked_actor_id=excluded.linked_actor_id,
                metadata_json=excluded.metadata_json,
                updated_at=CURRENT_TIMESTAMP
            """
            conn.execute(
                query,
                (
                    str(account.account_id),
                    account.provider,
                    str(account.provider_subject),
                    account.display_name,
                    linked_id,
                    metadata_json,
                ),
            )

        return account

    @override
    async def link_account_to_actor(
        self,
        *,
        account_id: AccountId,
        actor_id: ActorId,
    ) -> AccountProfile:
        """Link an account to an internal ActorId.

        Returns:
            AccountProfile: The updated account profile.

        Raises:
            AccountStoreError: If the account_id does not exist.
        """
        with self._transaction() as conn:
            cursor = conn.execute("SELECT * FROM accounts WHERE account_id = ?", (str(account_id),))
            row = cursor.fetchone()
            if not row:
                msg = f"Account not found: {account_id}"
                raise AccountStoreError(msg)

            query = (
                "UPDATE accounts SET linked_actor_id = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE account_id = ?"
            )
            conn.execute(query, (str(actor_id), str(account_id)))

            cursor = conn.execute("SELECT * FROM accounts WHERE account_id = ?", (str(account_id),))
            updated_row = cursor.fetchone()
            return self._row_to_profile(updated_row)

    @override
    async def unlink_account(
        self,
        account_id: AccountId,
    ) -> AccountProfile:
        """Remove any actor linking from an account.

        Returns:
            AccountProfile: The updated account profile.

        Raises:
            AccountStoreError: If the account_id does not exist.
        """
        with self._transaction() as conn:
            cursor = conn.execute("SELECT * FROM accounts WHERE account_id = ?", (str(account_id),))
            row = cursor.fetchone()
            if not row:
                msg = f"Account not found: {account_id}"
                raise AccountStoreError(msg)

            query = (
                "UPDATE accounts SET linked_actor_id = NULL, updated_at = CURRENT_TIMESTAMP "
                "WHERE account_id = ?"
            )
            conn.execute(query, (str(account_id),))

            cursor = conn.execute("SELECT * FROM accounts WHERE account_id = ?", (str(account_id),))
            updated_row = cursor.fetchone()
            return self._row_to_profile(updated_row)
