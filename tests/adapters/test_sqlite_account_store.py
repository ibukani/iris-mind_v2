"""SQLiteAccountStore tests."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import pytest

from iris.adapters.persistence.sqlite.stores.account import SQLiteAccountStore
from iris.contracts.accounts import AccountProfile, AccountStoreError
from iris.core.ids import AccountId, ActorId, ExternalRef

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.anyio
async def test_sqlite_account_store_put_and_get(tmp_path: Path) -> None:
    """Put and get_by_account_id/get_by_external_ref should work."""
    db_path = tmp_path / "accounts.db"
    store = SQLiteAccountStore(db_path)

    profile = AccountProfile(
        account_id=AccountId("acct-1"),
        provider="discord",
        provider_subject=ExternalRef("123"),
        display_name="Mina",
    )

    result = await store.put(profile)
    assert result == profile

    by_id = await store.get_by_account_id(AccountId("acct-1"))
    assert by_id == profile

    by_ref = await store.get_by_external_ref(
        provider="discord", provider_subject=ExternalRef("123")
    )
    assert by_ref == profile

    await store.close()


@pytest.mark.anyio
async def test_account_survives_reinstantiation(tmp_path: Path) -> None:
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
    await store1.put(profile)
    await store1.close()

    store2 = SQLiteAccountStore(db_path)
    fetched = await store2.get_by_account_id(AccountId("acct-1"))
    assert fetched == profile
    assert fetched is not None
    assert fetched.metadata == {"role": "admin"}
    await store2.close()


@pytest.mark.anyio
async def test_duplicate_account_id_conflict_is_rejected(tmp_path: Path) -> None:
    """Reject if account_id already exists with different provider/subject."""
    db_path = tmp_path / "accounts.db"
    store = SQLiteAccountStore(db_path)

    profile1 = AccountProfile(
        account_id=AccountId("acct-1"),
        provider="discord",
        provider_subject=ExternalRef("123"),
        display_name="Mina",
    )
    await store.put(profile1)

    profile2 = AccountProfile(
        account_id=AccountId("acct-1"),
        provider="github",
        provider_subject=ExternalRef("456"),
        display_name="Mina GitHub",
    )
    with pytest.raises(AccountStoreError, match="account_id conflict"):
        await store.put(profile2)

    await store.close()


@pytest.mark.anyio
async def test_duplicate_external_ref_conflict_is_rejected(tmp_path: Path) -> None:
    """Reject if provider/subject already exists with different account_id."""
    db_path = tmp_path / "accounts.db"
    store = SQLiteAccountStore(db_path)

    profile1 = AccountProfile(
        account_id=AccountId("acct-1"),
        provider="discord",
        provider_subject=ExternalRef("123"),
        display_name="Mina",
    )
    await store.put(profile1)

    profile2 = AccountProfile(
        account_id=AccountId("acct-2"),
        provider="discord",
        provider_subject=ExternalRef("123"),
        display_name="Mina Clone",
    )
    with pytest.raises(AccountStoreError, match="external ref conflict"):
        await store.put(profile2)

    await store.close()


@pytest.mark.anyio
async def test_update_linked_actor_id(tmp_path: Path) -> None:
    """Putting an account with updated linked_actor_id should persist."""
    db_path = tmp_path / "accounts.db"
    store = SQLiteAccountStore(db_path)

    profile = AccountProfile(
        account_id=AccountId("acct-1"),
        provider="discord",
        provider_subject=ExternalRef("123"),
        display_name="Mina",
    )
    await store.put(profile)

    updated = profile.model_copy(update={"linked_actor_id": ActorId("actor-mina")})
    await store.put(updated)
    await store.close()

    # Verify persistence across instances
    store2 = SQLiteAccountStore(db_path)
    fetched = await store2.get_by_account_id(AccountId("acct-1"))
    assert fetched is not None
    assert fetched.linked_actor_id == ActorId("actor-mina")

    # Unlink
    unlinked = fetched.model_copy(update={"linked_actor_id": None})
    await store2.put(unlinked)

    fetched_unlinked = await store2.get_by_account_id(AccountId("acct-1"))
    assert fetched_unlinked is not None
    assert fetched_unlinked.linked_actor_id is None
    await store2.close()
