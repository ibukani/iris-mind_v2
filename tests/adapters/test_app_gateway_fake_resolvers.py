"""AppGateway fake resolver implementations tests."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from iris.adapters.app_gateway.fake_resolvers import FakeIdentityResolver, FakeSpaceResolver
from iris.contracts.external_refs import ExternalAccountRef, ExternalSpaceRef
from iris.contracts.identity import ActorKind
from iris.contracts.spaces import SpaceKind
from iris.core.ids import AccountId, ActorId, DeviceId, ExternalRef

if TYPE_CHECKING:
    from iris.adapters.app_gateway.ports import IdentityResolver, SpaceResolver


def test_fake_identity_resolver_returns_stable_actor_id_for_same_external_ref() -> None:
    """同じprovider/provider_subjectが同じActorIdへ解決されることを確認する。"""
    resolver = FakeIdentityResolver()

    first = asyncio.run(
        resolver.resolve_identity(
            ExternalAccountRef(
                provider="discord",
                provider_subject=ExternalRef("123"),
                display_name="Mina",
            )
        )
    )
    second = asyncio.run(
        resolver.resolve_identity(
            ExternalAccountRef(
                provider="discord",
                provider_subject=ExternalRef("123"),
                display_name="Mina Renamed",
            )
        )
    )

    assert first.actor_id == second.actor_id
    assert first.account_id == second.account_id


def test_fake_identity_resolver_returns_different_actor_id_for_different_subject() -> None:
    """異なるprovider_subjectが異なるActorIdへ解決されることを確認する。"""
    resolver = FakeIdentityResolver()

    first = asyncio.run(
        resolver.resolve_identity(
            ExternalAccountRef(
                provider="discord",
                provider_subject=ExternalRef("123"),
                display_name="Mina",
            )
        )
    )
    second = asyncio.run(
        resolver.resolve_identity(
            ExternalAccountRef(
                provider="discord",
                provider_subject=ExternalRef("456"),
                display_name="Nao",
            )
        )
    )

    assert first.actor_id != second.actor_id
    assert first.account_id != second.account_id


def test_fake_identity_resolver_different_provider_same_subject() -> None:
    """異なるproviderで同じsubjectが異なるAccount/Actorへ解決されることを確認する。"""
    resolver = FakeIdentityResolver()

    first = asyncio.run(
        resolver.resolve_identity(
            ExternalAccountRef(
                provider="discord",
                provider_subject=ExternalRef("123"),
                display_name="Mina",
            )
        )
    )
    second = asyncio.run(
        resolver.resolve_identity(
            ExternalAccountRef(
                provider="slack",
                provider_subject=ExternalRef("123"),
                display_name="Mina",
            )
        )
    )

    assert first.actor_id != second.actor_id
    assert first.account_id != second.account_id


def test_fake_identity_resolver_links_multiple_accounts_to_same_actor() -> None:
    """同じActorIdに複数の外部アカウントがリンクされることを確認する。"""
    linked = {
        ("discord", "123"): ActorId("actor-ibuki"),
        ("cli", "ibuki"): ActorId("actor-ibuki"),
    }
    resolver = FakeIdentityResolver(linked_actor_ids=linked)

    discord_identity = asyncio.run(
        resolver.resolve_identity(
            ExternalAccountRef(
                provider="discord",
                provider_subject=ExternalRef("123"),
                display_name="Ibuki Discord",
            )
        )
    )
    cli_identity = asyncio.run(
        resolver.resolve_identity(
            ExternalAccountRef(
                provider="cli",
                provider_subject=ExternalRef("ibuki"),
                display_name="Ibuki CLI",
            )
        )
    )

    assert discord_identity.actor_id == "actor-ibuki"
    assert cli_identity.actor_id == "actor-ibuki"
    assert discord_identity.account_id != cli_identity.account_id


def test_fake_identity_resolver_preserves_identity_context_fields() -> None:
    """IdentityResolverが入力されたIdentity context fieldを保持することを確認する。"""
    resolver: IdentityResolver = FakeIdentityResolver()

    identity = asyncio.run(
        resolver.resolve_identity(
            ExternalAccountRef(
                provider="discord",
                provider_subject=ExternalRef("123"),
                display_name="Mina",
                actor_kind=ActorKind.DEVICE,
                account_id=AccountId("acct-1"),
                metadata={"role": "tester"},
            ),
            device_id=DeviceId("dev-1"),
        )
    )

    assert identity.provider == "discord"
    assert identity.provider_subject == ExternalRef("123")
    assert identity.display_name == "Mina"
    assert identity.actor_kind == ActorKind.DEVICE
    assert identity.account_id == AccountId("acct-1")
    assert identity.device_id == DeviceId("dev-1")
    assert identity.metadata == {"role": "tester"}


def test_fake_space_resolver_returns_stable_space_id_for_same_external_ref() -> None:
    """同じprovider/provider_space_refが同じSpaceIdへ解決されることを確認する。"""
    resolver = FakeSpaceResolver()

    first = asyncio.run(
        resolver.resolve_space(
            ExternalSpaceRef(
                provider="discord",
                provider_space_ref=ExternalRef("channel-1"),
                display_name="general",
                space_kind=SpaceKind.CHANNEL,
            )
        )
    )
    second = asyncio.run(
        resolver.resolve_space(
            ExternalSpaceRef(
                provider="discord",
                provider_space_ref=ExternalRef("channel-1"),
                display_name="general-renamed",
                space_kind=SpaceKind.CHANNEL,
            )
        )
    )

    assert first.space_id == second.space_id


def test_fake_space_resolver_preserves_space_fields_and_participants() -> None:
    """SpaceResolverがspace kind/display name/participants/metadataを保持することを確認する。"""
    identity = asyncio.run(
        FakeIdentityResolver().resolve_identity(
            ExternalAccountRef(
                provider="discord",
                provider_subject=ExternalRef("123"),
                display_name="Mina",
            )
        )
    )
    resolver: SpaceResolver = FakeSpaceResolver()

    space = asyncio.run(
        resolver.resolve_space(
            ExternalSpaceRef(
                provider="discord",
                provider_space_ref=ExternalRef("channel-1"),
                display_name="general",
                space_kind=SpaceKind.CHANNEL,
                metadata={"topic": "tea"},
            ),
            participants=(identity,),
        )
    )

    assert space.space_kind == SpaceKind.CHANNEL
    assert space.display_name == "general"
    assert space.metadata == {"topic": "tea"}
    assert len(space.participants) == 1
    assert space.participants[0].actor_id == identity.actor_id
    assert space.participants[0].identity == identity
