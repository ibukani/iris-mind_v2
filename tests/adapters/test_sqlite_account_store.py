"""SQLiteAccountStore tests."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from iris.adapters.accounts.sqlite import SQLiteAccountStore
from iris.contracts.accounts import AccountProfile, AccountStoreError
from iris.core.ids import AccountId, ActorId, ExternalRef

if TYPE_CHECKING:
    from pathlib import Path


def test_sqlite_account_store_put_and_get(tmp_path: Path) -> None:
    """Put and get_by_account_id/get_by_external_ref should work."""
    db_path = tmp_path / "accounts.db"
    store = SQLiteAccountStore(db_path)

    profile = AccountProfile(
        account_id=AccountId("acct-1"),
        provider="discord",
        provider_subject=ExternalRef("123"),
        display_name="Mina",
    )

    result = asyncio.run(store.put(profile))
    assert result == profile

    by_id = asyncio.run(store.get_by_account_id(AccountId("acct-1")))
    assert by_id == profile

    by_ref = asyncio.run(
        store.get_by_external_ref(provider="discord", provider_subject=ExternalRef("123"))
    )
    assert by_ref == profile


def test_account_survives_reinstantiation(tmp_path: Path) -> None:
    """Account and metadata should survive reopening the database."""
    db_path = tmp_path / "accounts.db"
    store1 = SQLiteAccountStore(db_path)

    profile = AccountProfile(
        account_id=AccountId("acct-1"),
        provider="discord",
        provider_subject=ExternalRef("123"),
        display_name="Mina",
        metadata={"role": "admin"},
    )
    asyncio.run(store1.put(profile))

    store2 = SQLiteAccountStore(db_path)
    fetched = asyncio.run(store2.get_by_account_id(AccountId("acct-1")))
    assert fetched == profile
    assert fetched is not None
    assert fetched.metadata == {"role": "admin"}


def test_duplicate_account_id_conflict_is_rejected(tmp_path: Path) -> None:
    """Reject if account_id already exists with different provider/subject."""
    db_path = tmp_path / "accounts.db"
    store = SQLiteAccountStore(db_path)

    profile1 = AccountProfile(
        account_id=AccountId("acct-1"),
        provider="discord",
        provider_subject=ExternalRef("123"),
        display_name="Mina",
    )
    asyncio.run(store.put(profile1))

    profile2 = AccountProfile(
        account_id=AccountId("acct-1"),
        provider="github",
        provider_subject=ExternalRef("456"),
        display_name="Mina GitHub",
    )
    with pytest.raises(AccountStoreError, match="account_id conflict"):
        asyncio.run(store.put(profile2))


def test_duplicate_external_ref_conflict_is_rejected(tmp_path: Path) -> None:
    """Reject if provider/subject already exists with different account_id."""
    db_path = tmp_path / "accounts.db"
    store = SQLiteAccountStore(db_path)

    profile1 = AccountProfile(
        account_id=AccountId("acct-1"),
        provider="discord",
        provider_subject=ExternalRef("123"),
        display_name="Mina",
    )
    asyncio.run(store.put(profile1))

    profile2 = AccountProfile(
        account_id=AccountId("acct-2"),
        provider="discord",
        provider_subject=ExternalRef("123"),
        display_name="Mina Clone",
    )
    with pytest.raises(AccountStoreError, match="external ref conflict"):
        asyncio.run(store.put(profile2))


def test_link_account_to_actor(tmp_path: Path) -> None:
    """link_account_to_actor should update linked_actor_id and persist."""
    db_path = tmp_path / "accounts.db"
    store = SQLiteAccountStore(db_path)

    profile = AccountProfile(
        account_id=AccountId("acct-1"),
        provider="discord",
        provider_subject=ExternalRef("123"),
        display_name="Mina",
    )
    asyncio.run(store.put(profile))

    linked = asyncio.run(
        store.link_account_to_actor(account_id=AccountId("acct-1"), actor_id=ActorId("actor-mina"))
    )
    assert linked.linked_actor_id == ActorId("actor-mina")

    # Verify persistence across instances
    store2 = SQLiteAccountStore(db_path)
    fetched = asyncio.run(store2.get_by_account_id(AccountId("acct-1")))
    assert fetched is not None
    assert fetched.linked_actor_id == ActorId("actor-mina")


def test_unlink_account(tmp_path: Path) -> None:
    """unlink_account should clear linked_actor_id and persist."""
    db_path = tmp_path / "accounts.db"
    store = SQLiteAccountStore(db_path)

    profile = AccountProfile(
        account_id=AccountId("acct-1"),
        provider="discord",
        provider_subject=ExternalRef("123"),
        display_name="Mina",
        linked_actor_id=ActorId("actor-mina"),
    )
    asyncio.run(store.put(profile))

    unlinked = asyncio.run(store.unlink_account(AccountId("acct-1")))
    assert unlinked.linked_actor_id is None

    # Verify persistence across instances
    store2 = SQLiteAccountStore(db_path)
    fetched = asyncio.run(store2.get_by_account_id(AccountId("acct-1")))
    assert fetched is not None
    assert fetched.linked_actor_id is None
