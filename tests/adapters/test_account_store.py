"""AccountStore tests."""

from __future__ import annotations

import asyncio
import dataclasses

import pytest

from iris.contracts.accounts import AccountProfile, AccountStoreError
from iris.core.ids import AccountId, ActorId, ExternalRef
from iris.runtime.state.ephemeral.accounts import InMemoryAccountStore


def test_in_memory_account_store_put_and_get() -> None:
    """Put and get_by_account_id/get_by_external_ref should work."""
    store = InMemoryAccountStore()

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


def test_duplicate_account_id_conflict_is_rejected() -> None:
    """Reject if account_id already exists with different provider/subject."""
    store = InMemoryAccountStore()

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


def test_duplicate_external_ref_conflict_is_rejected() -> None:
    """Reject if provider/subject already exists with different account_id."""
    store = InMemoryAccountStore()

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


def test_update_linked_actor_id() -> None:
    """Updating linked_actor_id should work."""
    store = InMemoryAccountStore()

    profile = AccountProfile(
        account_id=AccountId("acct-1"),
        provider="discord",
        provider_subject=ExternalRef("123"),
        display_name="Mina",
    )
    asyncio.run(store.put(profile))

    updated = dataclasses.replace(profile, linked_actor_id=ActorId("actor-mina"))
    linked = asyncio.run(store.put(updated))
    assert linked.linked_actor_id == ActorId("actor-mina")

    # Verify persistence
    fetched = asyncio.run(store.get_by_account_id(AccountId("acct-1")))
    assert fetched is not None
    assert fetched.linked_actor_id == ActorId("actor-mina")

    # Unlink
    unlinked_profile = dataclasses.replace(fetched, linked_actor_id=None)
    unlinked = asyncio.run(store.put(unlinked_profile))
    assert unlinked.linked_actor_id is None

    # Verify persistence
    fetched_unlinked = asyncio.run(store.get_by_account_id(AccountId("acct-1")))
    assert fetched_unlinked is not None
    assert fetched_unlinked.linked_actor_id is None


def test_account_metadata_is_preserved() -> None:
    """Metadata should be preserved upon put."""
    store = InMemoryAccountStore()

    profile = AccountProfile(
        account_id=AccountId("acct-1"),
        provider="discord",
        provider_subject=ExternalRef("123"),
        display_name="Mina",
        metadata={"role": "admin"},
    )
    asyncio.run(store.put(profile))

    fetched = asyncio.run(store.get_by_account_id(AccountId("acct-1")))
    assert fetched is not None
    assert fetched.metadata == {"role": "admin"}
