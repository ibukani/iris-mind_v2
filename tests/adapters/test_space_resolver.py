"""Tests for SpaceResolver implementations."""

from __future__ import annotations

import pytest

from iris.adapters.app_gateway.space_resolver import SpaceBindingAwareSpaceResolver
from iris.adapters.spaces.memory import InMemorySpaceBindingStore
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.spaces import SpaceBinding, SpaceKind
from iris.core.ids import ActorId, ExternalRef, SpaceId


@pytest.fixture
def binding_store() -> InMemorySpaceBindingStore:
    """Return an empty InMemorySpaceBindingStore."""
    return InMemorySpaceBindingStore()


@pytest.fixture
def resolver(binding_store: InMemorySpaceBindingStore) -> SpaceBindingAwareSpaceResolver:
    """Return a SpaceBindingAwareSpaceResolver."""
    return SpaceBindingAwareSpaceResolver(binding_store=binding_store)


@pytest.mark.asyncio
async def test_binding_hit_returns_bound_space_id(
    resolver: SpaceBindingAwareSpaceResolver,
    binding_store: InMemorySpaceBindingStore,
) -> None:
    """Test that existing binding returns the bound SpaceId."""
    await binding_store.put(
        SpaceBinding(
            provider="discord",
            provider_space_ref=ExternalRef("123"),
            space_id=SpaceId("bound-space-1"),
            display_name="Bound Channel",
            space_kind=SpaceKind.CHANNEL,
            metadata={"guild_id": "999"},
        )
    )

    space = await resolver.resolve_space(
        provider="discord",
        provider_space_ref=ExternalRef("123"),
        display_name="Input Channel",
        space_kind=SpaceKind.ROOM,
        metadata={"input_meta": "yes"},
    )

    assert space.space_id == "bound-space-1"
    assert space.display_name == "Bound Channel"
    assert space.space_kind == SpaceKind.CHANNEL
    assert space.metadata == {"input_meta": "yes", "guild_id": "999"}


@pytest.mark.asyncio
async def test_missing_binding_returns_deterministic_fallback(
    resolver: SpaceBindingAwareSpaceResolver,
) -> None:
    """Test that missing binding generates deterministic fallback SpaceId."""
    space1 = await resolver.resolve_space(
        provider="discord",
        provider_space_ref=ExternalRef("missing-123"),
        display_name="Missing Channel",
        space_kind=SpaceKind.CHANNEL,
    )
    space2 = await resolver.resolve_space(
        provider="discord",
        provider_space_ref=ExternalRef("missing-123"),
        display_name="Missing Channel",
        space_kind=SpaceKind.CHANNEL,
    )

    assert space1.space_id == space2.space_id
    assert space1.space_id.startswith("space-discord-")
    assert space1.display_name == "Missing Channel"
    assert space1.space_kind == SpaceKind.CHANNEL


@pytest.mark.asyncio
async def test_different_ref_returns_different_fallback(
    resolver: SpaceBindingAwareSpaceResolver,
) -> None:
    """Test that different refs generate different fallback SpaceIds."""
    space1 = await resolver.resolve_space(
        provider="discord",
        provider_space_ref=ExternalRef("missing-1"),
        display_name="C1",
        space_kind=SpaceKind.CHANNEL,
    )
    space2 = await resolver.resolve_space(
        provider="discord",
        provider_space_ref=ExternalRef("missing-2"),
        display_name="C2",
        space_kind=SpaceKind.CHANNEL,
    )

    assert space1.space_id != space2.space_id


@pytest.mark.asyncio
async def test_participants_converted_to_snapshots(
    resolver: SpaceBindingAwareSpaceResolver,
) -> None:
    """Test that participants are correctly snapshotted in the resolved space."""
    actor = Identity(
        actor_id=ActorId("actor-1"),
        actor_kind=ActorKind.HUMAN,
        display_name="Alice",
        metadata={"key": "val"},
    )

    space = await resolver.resolve_space(
        provider="discord",
        provider_space_ref=ExternalRef("123"),
        display_name="Channel",
        space_kind=SpaceKind.CHANNEL,
        participants=[actor],
    )

    assert len(space.participants) == 1
    p = space.participants[0]
    assert p.actor_id == "actor-1"
    assert p.participant_kind == "human"
    assert p.display_name == "Alice"
    assert p.identity == actor
    assert p.metadata == {"key": "val"}
