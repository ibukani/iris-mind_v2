"""アカウントと ID 解決のランタイムワイヤリング。"""

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
    """永続 SQLite アカウントストアをバックエンドとする IdentityResolver を構築する。

    Args:
        db_path: SQLite データベースファイルへのパス。

    Returns:
        IdentityResolver: 構成済みの AccountBackedIdentityResolver。
    """
    account_store = SQLiteAccountStore(db_path)
    return AccountBackedIdentityResolver(account_store=account_store)
