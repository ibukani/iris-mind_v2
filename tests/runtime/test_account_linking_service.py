"""AccountLinkingService tests."""

from __future__ import annotations

import asyncio

from iris.adapters.accounts.memory import InMemoryAccountStore
from iris.contracts.accounts import AccountProfile
from iris.core.ids import AccountId, ActorId, ExternalRef
from iris.runtime.accounts import AccountLinkingService


def test_account_linking_service_delegates_to_store() -> None:
    """Service methods should delegate to the underlying store."""
    store = InMemoryAccountStore()
    service = AccountLinkingService(store)

    profile = AccountProfile(
        account_id=AccountId("acct-1"),
        provider="discord",
        provider_subject=ExternalRef("123"),
        display_name="Mina",
    )
    asyncio.run(store.put(profile))

    # get_account_by_id
    by_id = asyncio.run(service.get_account_by_id(AccountId("acct-1")))
    assert by_id == profile

    # get_account_by_external_ref
    by_ref = asyncio.run(
        service.get_account_by_external_ref(provider="discord", provider_subject=ExternalRef("123"))
    )
    assert by_ref == profile

    # link_account_to_actor
    linked = asyncio.run(
        service.link_account_to_actor(
            account_id=AccountId("acct-1"), actor_id=ActorId("actor-mina")
        )
    )
    assert linked.linked_actor_id == ActorId("actor-mina")

    # unlink_account
    unlinked = asyncio.run(service.unlink_account(AccountId("acct-1")))
    assert unlinked.linked_actor_id is None
