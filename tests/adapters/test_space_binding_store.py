"""Tests for SpaceBindingStore implementations."""

from __future__ import annotations

import pytest

from iris.adapters.spaces.memory import InMemorySpaceBindingStore
from iris.contracts.spaces import SpaceBinding, SpaceBindingStoreError, SpaceKind
from iris.core.ids import ExternalRef, SpaceId


@pytest.fixture
def store() -> InMemorySpaceBindingStore:
    """Return an empty InMemorySpaceBindingStore."""
    return InMemorySpaceBindingStore()


@pytest.mark.asyncio
async def test_in_memory_put_and_get(store: InMemorySpaceBindingStore) -> None:
    """Test put and get_by_external_ref methods."""
    binding = SpaceBinding(
        provider="discord",
        provider_space_ref=ExternalRef("123"),
        space_id=SpaceId("space-1"),
        display_name="General",
        space_kind=SpaceKind.CHANNEL,
    )

    await store.put(binding)
    retrieved = await store.get_by_external_ref(
        provider="discord",
        provider_space_ref=ExternalRef("123"),
    )

    assert retrieved == binding


@pytest.mark.asyncio
async def test_in_memory_missing_ref_returns_none(store: InMemorySpaceBindingStore) -> None:
    """Test that missing ref returns None."""
    retrieved = await store.get_by_external_ref(
        provider="discord",
        provider_space_ref=ExternalRef("missing"),
    )

    assert retrieved is None


@pytest.mark.asyncio
async def test_in_memory_duplicate_ref_different_space_id_raises(
    store: InMemorySpaceBindingStore,
) -> None:
    """Test that duplicate ref with different space_id raises an error."""
    binding1 = SpaceBinding(
        provider="discord",
        provider_space_ref=ExternalRef("123"),
        space_id=SpaceId("space-1"),
        display_name="General",
        space_kind=SpaceKind.CHANNEL,
    )
    binding2 = SpaceBinding(
        provider="discord",
        provider_space_ref=ExternalRef("123"),
        space_id=SpaceId("space-2"),
        display_name="General2",
        space_kind=SpaceKind.CHANNEL,
    )

    await store.put(binding1)

    with pytest.raises(SpaceBindingStoreError):
        await store.put(binding2)


@pytest.mark.asyncio
async def test_in_memory_metadata_is_preserved(store: InMemorySpaceBindingStore) -> None:
    """Test that metadata is preserved when saved and retrieved."""
    binding = SpaceBinding(
        provider="discord",
        provider_space_ref=ExternalRef("123"),
        space_id=SpaceId("space-1"),
        display_name="General",
        space_kind=SpaceKind.CHANNEL,
        metadata={"guild_id": "999"},
    )

    await store.put(binding)
    retrieved = await store.get_by_external_ref(
        provider="discord",
        provider_space_ref=ExternalRef("123"),
    )

    assert retrieved is not None
    assert retrieved.metadata == {"guild_id": "999"}
