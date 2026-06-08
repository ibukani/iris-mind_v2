"""Tests for accounts runtime wiring."""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.adapters.accounts.sqlite import SQLiteAccountStore
from iris.adapters.app_gateway.identity_resolver import AccountBackedIdentityResolver
from iris.runtime.wiring.accounts import build_identity_resolver_with_sqlite_account_store
from tests.helpers.private_access import get_private_attr

if TYPE_CHECKING:
    from pathlib import Path


def test_build_identity_resolver_with_sqlite_account_store(tmp_path: Path) -> None:
    """build_identity_resolver_with_sqlite_account_store returns a wired resolver."""
    db_path = tmp_path / "accounts.db"
    resolver = build_identity_resolver_with_sqlite_account_store(db_path)

    assert isinstance(resolver, AccountBackedIdentityResolver)
    assert isinstance(
        get_private_attr(resolver, "_account_store"),
        SQLiteAccountStore,
    )
