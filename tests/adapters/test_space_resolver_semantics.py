"""Space resolver semantic tests."""

from __future__ import annotations

import pytest

from iris.adapters.app_gateway.space_resolver import EphemeralSpaceResolver
from iris.adapters.app_gateway.stable_ids import stable_space_id
from iris.contracts.external_refs import ExternalSpaceRef
from iris.contracts.spaces import SpaceKind
from iris.core.ids import ExternalRef


@pytest.mark.anyio
async def test_same_provider_and_space_ref_return_same_space_id() -> None:
    """同じprovider/provider_space_refは同じspace_idへ解決される。"""
    resolver = EphemeralSpaceResolver()

    first = await resolver.resolve_space(_space_ref(display_name="initial"))
    second = await resolver.resolve_space(_space_ref(display_name="renamed"))

    assert first.space_id == second.space_id
    assert first.space_id == stable_space_id("discord", ExternalRef("channel-1"))


@pytest.mark.anyio
async def test_different_provider_returns_different_space_id() -> None:
    """providerが違えば同じprovider_space_refでもspace_idは変わる。"""
    resolver = EphemeralSpaceResolver()

    first = await resolver.resolve_space(_space_ref(provider="discord"))
    second = await resolver.resolve_space(_space_ref(provider="slack"))

    assert first.space_id != second.space_id


@pytest.mark.anyio
async def test_different_provider_space_ref_returns_different_space_id() -> None:
    """provider_space_refが違えばspace_idは変わる。"""
    resolver = EphemeralSpaceResolver()

    first = await resolver.resolve_space(_space_ref(provider_space_ref="channel-1"))
    second = await resolver.resolve_space(_space_ref(provider_space_ref="channel-2"))

    assert first.space_id != second.space_id


@pytest.mark.anyio
async def test_display_name_metadata_and_kind_do_not_affect_space_id() -> None:
    """表示名、metadata、space_kindはspace_id算出に使わない。"""
    resolver = EphemeralSpaceResolver()

    first = await resolver.resolve_space(
        _space_ref(
            display_name="General",
            space_kind=SpaceKind.TEXT_CHANNEL,
            metadata={"topic": "initial"},
        ),
    )
    second = await resolver.resolve_space(
        _space_ref(
            display_name="Renamed",
            space_kind=SpaceKind.THREAD,
            metadata={"topic": "changed"},
        ),
    )

    assert first.space_id == second.space_id
    assert second.display_name == "Renamed"
    assert second.space_kind is SpaceKind.THREAD
    assert second.metadata == {"topic": "changed"}


@pytest.mark.anyio
async def test_interaction_space_does_not_own_current_occupants() -> None:
    """Space解決結果に現在の在室者フィールドが存在しないことを確認する。"""
    resolver = EphemeralSpaceResolver()

    space = await resolver.resolve_space(_space_ref())

    assert not hasattr(space, "participants")


@pytest.mark.anyio
async def test_ephemeral_resolver_requires_no_persistence_store() -> None:
    """EphemeralSpaceResolverは永続storeなしで決定論的に解決する。"""
    resolver = EphemeralSpaceResolver()

    space = await resolver.resolve_space(_space_ref())

    assert not hasattr(resolver, "_binding_store")
    assert space.space_id == stable_space_id("discord", ExternalRef("channel-1"))


def _space_ref(
    *,
    provider: str = "discord",
    provider_space_ref: str = "channel-1",
    display_name: str = "General",
    space_kind: SpaceKind = SpaceKind.TEXT_CHANNEL,
    metadata: dict[str, str] | None = None,
) -> ExternalSpaceRef:
    return ExternalSpaceRef(
        provider=provider,
        provider_space_ref=ExternalRef(provider_space_ref),
        display_name=display_name,
        space_kind=space_kind,
        metadata=metadata or {},
    )
