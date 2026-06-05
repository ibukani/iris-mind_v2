"""Runtime wiring for accounts and identity resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.adapters.accounts.sqlite import SQLiteAccountStore
from iris.adapters.app_gateway.identity_resolver import AccountBackedIdentityResolver

if TYPE_CHECKING:
    from pathlib import Path

    from iris.adapters.app_gateway.ports import IdentityResolver


def build_identity_resolver_with_sqlite_account_store(
    db_path: str | Path,
) -> IdentityResolver:
    """Build an IdentityResolver backed by a persistent SQLite account store.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        IdentityResolver: A configured AccountBackedIdentityResolver.
    """
    account_store = SQLiteAccountStore(db_path)
    return AccountBackedIdentityResolver(account_store=account_store)
