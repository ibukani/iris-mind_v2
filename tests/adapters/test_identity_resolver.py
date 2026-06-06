"""AccountBackedIdentityResolver tests."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from iris.adapters.accounts.sqlite import SQLiteAccountStore
from iris.adapters.app_gateway.identity_resolver import AccountBackedIdentityResolver
from iris.contracts.external_refs import ExternalAccountRef
from iris.core.ids import ActorId, DeviceId, ExternalRef

if TYPE_CHECKING:
    from pathlib import Path


def test_account_backed_resolver_persists_identity_across_restarts(tmp_path: Path) -> None:
    """Identity resolution should be stable across store re-instantiation."""
    db_path = tmp_path / "accounts.db"

    store1 = SQLiteAccountStore(db_path)
    resolver1 = AccountBackedIdentityResolver(store1)

    # First resolve creates the account
    identity1 = asyncio.run(
        resolver1.resolve_identity(
            ExternalAccountRef(
                provider="discord",
                provider_subject=ExternalRef("123"),
                display_name="Mina",
            )
        )
    )

    # Restart the app
    store2 = SQLiteAccountStore(db_path)
    resolver2 = AccountBackedIdentityResolver(store2)

    # Second resolve should fetch the same account
    identity2 = asyncio.run(
        resolver2.resolve_identity(
            ExternalAccountRef(
                provider="discord",
                provider_subject=ExternalRef("123"),
                display_name="Mina Updated",
            )
        )
    )

    assert identity1.account_id == identity2.account_id
    assert identity1.actor_id == identity2.actor_id


def test_account_backed_resolver_uses_linked_actor_id(tmp_path: Path) -> None:
    """Resolver should use linked_actor_id if present."""
    db_path = tmp_path / "accounts.db"

    store = SQLiteAccountStore(db_path)
    resolver = AccountBackedIdentityResolver(store)

    # Create the account by resolving it once
    identity1 = asyncio.run(
        resolver.resolve_identity(
            ExternalAccountRef(
                provider="discord",
                provider_subject=ExternalRef("123"),
                display_name="Mina",
            )
        )
    )

    assert identity1.account_id is not None

    # Link it
    asyncio.run(
        store.link_account_to_actor(account_id=identity1.account_id, actor_id=ActorId("actor-mina"))
    )

    # Restart and resolve again
    store2 = SQLiteAccountStore(db_path)
    resolver2 = AccountBackedIdentityResolver(store2)

    identity2 = asyncio.run(
        resolver2.resolve_identity(
            ExternalAccountRef(
                provider="discord",
                provider_subject=ExternalRef("123"),
                display_name="Mina",
            )
        )
    )

    assert identity2.account_id == identity1.account_id
    assert identity2.actor_id == ActorId("actor-mina")


def test_account_backed_resolver_updates_display_name(tmp_path: Path) -> None:
    """Resolver should update display_name if it changes in external ref."""
    db_path = tmp_path / "accounts.db"

    store = SQLiteAccountStore(db_path)
    resolver = AccountBackedIdentityResolver(store)

    identity1 = asyncio.run(
        resolver.resolve_identity(
            ExternalAccountRef(
                provider="discord",
                provider_subject=ExternalRef("123"),
                display_name="Mina Old",
            )
        )
    )

    assert identity1.display_name == "Mina Old"

    identity2 = asyncio.run(
        resolver.resolve_identity(
            ExternalAccountRef(
                provider="discord",
                provider_subject=ExternalRef("123"),
                display_name="Mina New",
            )
        )
    )

    assert identity2.display_name == "Mina New"


def test_account_backed_resolver_passes_device_id(tmp_path: Path) -> None:
    """Resolver should pass device_id to Identity."""
    db_path = tmp_path / "accounts.db"

    store = SQLiteAccountStore(db_path)
    resolver = AccountBackedIdentityResolver(store)

    identity = asyncio.run(
        resolver.resolve_identity(
            ExternalAccountRef(
                provider="discord",
                provider_subject=ExternalRef("123"),
                display_name="Mina",
            ),
            device_id=DeviceId("dev-1"),
        )
    )

    assert identity.device_id == "dev-1"
