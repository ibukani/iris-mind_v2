"""Account, Actor, and Identity resolver semantics tests."""

from __future__ import annotations

import dataclasses

import pytest

from iris.adapters.app_gateway.identity_resolver import AccountBackedIdentityResolver
from iris.contracts.accounts import AccountProfile, AccountStoreError
from iris.contracts.external_refs import ExternalAccountRef
from iris.contracts.identity import ActorKind
from iris.core.ids import AccountId, ActorId, ExternalRef
from iris.runtime.state.ephemeral.accounts import InMemoryAccountStore


@pytest.mark.anyio
async def test_same_external_account_resolves_to_same_account_and_actor() -> None:
    """同じprovider + subjectは同じaccount_idとprovisional actor_idに解決される。"""
    resolver = AccountBackedIdentityResolver(account_store=InMemoryAccountStore())

    first = await resolver.resolve_identity(_account_ref(display_name="Mina"))
    second = await resolver.resolve_identity(_account_ref(display_name="Mina"))

    assert second.account_id == first.account_id
    assert second.actor_id == first.actor_id


@pytest.mark.anyio
async def test_display_name_change_updates_name_without_changing_actor() -> None:
    """display_name変更はactor_idを変えない。"""
    store = InMemoryAccountStore()
    resolver = AccountBackedIdentityResolver(account_store=store)

    first = await resolver.resolve_identity(_account_ref(display_name="Mina"))
    second = await resolver.resolve_identity(_account_ref(display_name="Renamed Mina"))

    assert second.actor_id == first.actor_id
    assert second.display_name == "Renamed Mina"
    stored = await store.get_by_external_ref(
        provider="discord",
        provider_subject=ExternalRef("user-1"),
    )
    assert stored is not None
    assert stored.display_name == "Renamed Mina"


@pytest.mark.anyio
async def test_different_providers_with_same_subject_resolve_to_different_accounts() -> None:
    """同じsubjectでもproviderが違えば別accountになる。"""
    resolver = AccountBackedIdentityResolver(account_store=InMemoryAccountStore())

    cli = await resolver.resolve_identity(_account_ref(provider="cli"))
    discord = await resolver.resolve_identity(_account_ref(provider="discord"))

    assert cli.account_id != discord.account_id
    assert cli.actor_id != discord.actor_id


@pytest.mark.anyio
async def test_linked_actor_id_takes_precedence_and_unlink_restores_provisional() -> None:
    """linked_actor_idは優先され、unlink後はprovisional actor_idへ戻る。"""
    store = InMemoryAccountStore()
    resolver = AccountBackedIdentityResolver(account_store=store)
    initial = await resolver.resolve_identity(_account_ref())
    account_id = initial.account_id
    assert account_id is not None

    profile = await store.get_by_account_id(account_id)
    assert profile is not None
    linked_profile = dataclasses.replace(profile, linked_actor_id=ActorId("actor-linked"))
    await store.put(linked_profile)

    linked = await resolver.resolve_identity(_account_ref())

    profile = await store.get_by_account_id(account_id)
    assert profile is not None
    unlinked_profile = dataclasses.replace(profile, linked_actor_id=None)
    await store.put(unlinked_profile)

    unlinked = await resolver.resolve_identity(_account_ref())

    assert linked.actor_id == ActorId("actor-linked")
    assert unlinked.actor_id == initial.actor_id


@pytest.mark.anyio
@pytest.mark.parametrize(
    "actor_kind",
    [
        ActorKind.HUMAN,
        ActorKind.SERVICE,
        ActorKind.SYSTEM,
        ActorKind.DEVICE,
        ActorKind.IRIS,
    ],
)
async def test_actor_kind_is_preserved(actor_kind: ActorKind) -> None:
    """account_refのactor_kindはIdentityに保持される。"""
    resolver = AccountBackedIdentityResolver(account_store=InMemoryAccountStore())

    identity = await resolver.resolve_identity(_account_ref(actor_kind=actor_kind))

    assert identity.actor_kind is actor_kind


@pytest.mark.anyio
async def test_metadata_survives_account_creation_and_identity_resolution() -> None:
    """metadataはaccount作成とidentity解決で保持される。"""
    resolver = AccountBackedIdentityResolver(account_store=InMemoryAccountStore())

    identity = await resolver.resolve_identity(_account_ref(metadata={"role": "tester"}))

    assert identity.metadata == {"role": "tester"}


@pytest.mark.anyio
async def test_account_conflicts_raise_account_store_error() -> None:
    """同じaccount_idで別external refを保存するとAccountStoreErrorになる。"""
    store = InMemoryAccountStore(
        (
            AccountProfile(
                account_id=AccountId("account-fixed"),
                provider="discord",
                provider_subject=ExternalRef("user-1"),
                display_name="Mina",
            ),
        )
    )

    with pytest.raises(AccountStoreError, match="account_id conflict"):
        await store.put(
            AccountProfile(
                account_id=AccountId("account-fixed"),
                provider="cli",
                provider_subject=ExternalRef("user-1"),
                display_name="Mina",
            )
        )


def _account_ref(
    *,
    provider: str = "discord",
    provider_subject: ExternalRef | None = None,
    display_name: str = "Mina",
    actor_kind: ActorKind = ActorKind.HUMAN,
    metadata: dict[str, str] | None = None,
) -> ExternalAccountRef:
    return ExternalAccountRef(
        provider=provider,
        provider_subject=provider_subject or ExternalRef("user-1"),
        display_name=display_name,
        actor_kind=actor_kind,
        metadata=metadata or {},
    )
