"""AccountBackedIdentityResolver tests."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import pytest

from iris.adapters.app_gateway.identity_resolver import AccountBackedIdentityResolver
from iris.adapters.persistence.sqlite.stores.account import SQLiteAccountStore
from iris.contracts.external_refs import ExternalAccountRef
from iris.core.ids import ActorId, DeviceId, ExternalRef

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

pytestmark = pytest.mark.anyio


@pytest.fixture
async def store(tmp_path: Path) -> AsyncGenerator[SQLiteAccountStore]:
    """Provide a SQLiteAccountStore for testing.

    Yields:
        Configured store instance.
    """
    db_path = tmp_path / "accounts.db"
    s = SQLiteAccountStore(db_path)
    yield s
    await s.close()


async def test_account_backed_resolver_persists_identity_across_restarts(
    tmp_path: Path, store: SQLiteAccountStore
) -> None:
    """Identity resolution should be stable across store re-instantiation."""
    resolver1 = AccountBackedIdentityResolver(store)

    # First resolve creates the account
    identity1 = await resolver1.resolve_identity(
        ExternalAccountRef(
            provider="discord",
            provider_subject=ExternalRef("123"),
            display_name="Mina",
        )
    )

    # Restart the app
    db_path = tmp_path / "accounts.db"
    store2 = SQLiteAccountStore(db_path)
    resolver2 = AccountBackedIdentityResolver(store2)

    try:
        # Second resolve should fetch the same account
        identity2 = await resolver2.resolve_identity(
            ExternalAccountRef(
                provider="discord",
                provider_subject=ExternalRef("123"),
                display_name="Mina Updated",
            )
        )

        assert identity1.account_id == identity2.account_id
        assert identity1.actor_id == identity2.actor_id
    finally:
        await store2.close()


async def test_account_backed_resolver_uses_linked_actor_id(
    tmp_path: Path, store: SQLiteAccountStore
) -> None:
    """Resolver should use linked_actor_id if present."""
    resolver = AccountBackedIdentityResolver(store)

    # Create the account by resolving it once
    identity1 = await resolver.resolve_identity(
        ExternalAccountRef(
            provider="discord",
            provider_subject=ExternalRef("123"),
            display_name="Mina",
        )
    )

    assert identity1.account_id is not None

    profile = await store.get_by_account_id(identity1.account_id)
    assert profile is not None
    updated_profile = dataclasses.replace(profile, linked_actor_id=ActorId("actor-mina"))
    await store.put(updated_profile)

    # Restart and resolve again
    db_path = tmp_path / "accounts.db"
    store2 = SQLiteAccountStore(db_path)
    resolver2 = AccountBackedIdentityResolver(store2)

    try:
        identity2 = await resolver2.resolve_identity(
            ExternalAccountRef(
                provider="discord",
                provider_subject=ExternalRef("123"),
                display_name="Mina",
            )
        )

        assert identity2.account_id == identity1.account_id
        assert identity2.actor_id == ActorId("actor-mina")
    finally:
        await store2.close()


async def test_account_backed_resolver_updates_display_name(store: SQLiteAccountStore) -> None:
    """Resolver should update display_name if it changes in external ref."""
    resolver = AccountBackedIdentityResolver(store)

    identity1 = await resolver.resolve_identity(
        ExternalAccountRef(
            provider="discord",
            provider_subject=ExternalRef("123"),
            display_name="Mina Old",
        )
    )

    assert identity1.display_name == "Mina Old"

    identity2 = await resolver.resolve_identity(
        ExternalAccountRef(
            provider="discord",
            provider_subject=ExternalRef("123"),
            display_name="Mina New",
        )
    )

    assert identity2.display_name == "Mina New"


async def test_account_backed_resolver_passes_device_id(store: SQLiteAccountStore) -> None:
    """Resolver should pass device_id to Identity."""
    resolver = AccountBackedIdentityResolver(store)

    identity = await resolver.resolve_identity(
        ExternalAccountRef(
            provider="discord",
            provider_subject=ExternalRef("123"),
            display_name="Mina",
        ),
        device_id=DeviceId("dev-1"),
    )

    assert identity.device_id == "dev-1"
