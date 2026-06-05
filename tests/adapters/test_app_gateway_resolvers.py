"""Tests for App Gateway resolvers."""

from __future__ import annotations

import pytest

from iris.adapters.accounts.memory import InMemoryAccountStore
from iris.adapters.app_gateway.resolvers import AccountIdentityResolver, EphemeralSpaceResolver
from iris.contracts.spaces import SpaceKind
from iris.core.ids import ActorId, ExternalRef


@pytest.mark.anyio
async def test_account_identity_resolver_creates_account() -> None:
    """Test AccountIdentityResolver creates new account when missing."""
    store = InMemoryAccountStore()
    resolver = AccountIdentityResolver(store)

    identity = await resolver.resolve_identity(
        provider="discord",
        provider_subject=ExternalRef("u1"),
        display_name="User1",
    )

    assert identity.provider == "discord"
    assert identity.provider_subject == "u1"
    assert identity.display_name == "User1"
    assert identity.account_id is not None
    assert identity.actor_id is not None

    # Resolving again returns the same account
    identity2 = await resolver.resolve_identity(
        provider="discord",
        provider_subject=ExternalRef("u1"),
        display_name="User1_Updated",
    )

    assert identity.account_id == identity2.account_id
    assert identity2.display_name == "User1_Updated"


@pytest.mark.anyio
async def test_account_identity_resolver_respects_linked_actor() -> None:
    """Test AccountIdentityResolver returns linked actor ID if available."""
    store = InMemoryAccountStore()
    resolver = AccountIdentityResolver(store)

    identity = await resolver.resolve_identity(
        provider="discord",
        provider_subject=ExternalRef("u1"),
        display_name="User1",
    )

    assert identity.account_id is not None
    custom_actor_id = ActorId("actor-custom")
    await store.link_account_to_actor(account_id=identity.account_id, actor_id=custom_actor_id)

    identity2 = await resolver.resolve_identity(
        provider="discord",
        provider_subject=ExternalRef("u1"),
        display_name="User1",
    )

    assert identity2.actor_id == custom_actor_id


@pytest.mark.anyio
async def test_ephemeral_space_resolver() -> None:
    """Test EphemeralSpaceResolver creates deterministic SpaceId."""
    resolver = EphemeralSpaceResolver()

    space = await resolver.resolve_space(
        provider="discord",
        provider_space_ref=ExternalRef("c1"),
        display_name="Channel 1",
        space_kind=SpaceKind.CHANNEL,
    )

    assert space.space_kind == SpaceKind.CHANNEL
    assert space.display_name == "Channel 1"
    assert space.space_id is not None
    assert space.space_id.startswith("space-")

    # Resolving again returns the same space_id
    space2 = await resolver.resolve_space(
        provider="discord",
        provider_space_ref=ExternalRef("c1"),
        display_name="Channel 1",
        space_kind=SpaceKind.CHANNEL,
    )
    assert space.space_id == space2.space_id
