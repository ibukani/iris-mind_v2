"""SpaceResolver implementation tests."""

from __future__ import annotations

import pytest

from iris.adapters.app_gateway.space_resolver import EphemeralSpaceResolver
from iris.contracts.external_refs import ExternalSpaceRef
from iris.contracts.spaces import SpaceKind
from iris.core.ids import ExternalRef


@pytest.mark.anyio
async def test_ephemeral_space_resolver_returns_deterministic_id() -> None:
    """EphemeralSpaceResolver returns a stable deterministic SpaceId."""
    resolver = EphemeralSpaceResolver()

    space1 = await resolver.resolve_space(
        ExternalSpaceRef(
            provider="test-provider",
            provider_space_ref=ExternalRef("room-1"),
            display_name="Room One",
            space_kind=SpaceKind.ROOM,
        ),
    )
    space2 = await resolver.resolve_space(
        ExternalSpaceRef(
            provider="test-provider",
            provider_space_ref=ExternalRef("room-1"),
            display_name="Room One Different Name",
            space_kind=SpaceKind.ROOM,
        ),
    )

    assert space1.space_id == space2.space_id
    assert space1.space_id.startswith("space-test-provider-")
    assert space1.display_name == "Room One"


@pytest.mark.anyio
async def test_ephemeral_space_resolver_returns_stable_context_without_occupants() -> None:
    """EphemeralSpaceResolverが在室者を持たない安定contextを返すことを確認する。"""
    resolver = EphemeralSpaceResolver()

    space = await resolver.resolve_space(
        ExternalSpaceRef(
            provider="discord",
            provider_space_ref=ExternalRef("123"),
            display_name="Channel",
            space_kind=SpaceKind.TEXT_CHANNEL,
            metadata={"key": "val"},
        ),
    )

    assert space.space_kind is SpaceKind.TEXT_CHANNEL
    assert space.metadata == {"key": "val"}
    assert not hasattr(space, "participants")
