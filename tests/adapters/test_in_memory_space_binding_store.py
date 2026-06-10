"""In-memory SpaceBindingStore tests."""

from __future__ import annotations

import pytest

from iris.adapters.spaces.memory import InMemorySpaceBindingStore
from iris.contracts.spaces import SpaceBinding, SpaceBindingStoreError, SpaceKind
from iris.core.ids import ExternalRef, SpaceId


@pytest.mark.anyio
async def test_put_then_get_returns_binding() -> None:
    """put後にexternal refで同じbindingを取得できる。"""
    store = InMemorySpaceBindingStore()
    binding = _binding(metadata={"topic": "general"})

    await store.put(binding)

    result = await store.get_by_external_ref(
        provider="discord",
        provider_space_ref=ExternalRef("1"),
    )
    assert result == binding


@pytest.mark.anyio
async def test_same_external_ref_can_update_display_name_and_metadata() -> None:
    """同じexternal refは表示名とmetadataを更新できる。"""
    store = InMemorySpaceBindingStore()
    await store.put(_binding(display_name="old", metadata={"a": "1"}))
    updated = _binding(display_name="new", metadata={"b": "2"})

    result = await store.put(updated)

    assert result.display_name == "new"
    assert result.metadata == {"b": "2"}


@pytest.mark.anyio
async def test_different_external_ref_cannot_reuse_space_id() -> None:
    """別external refによるspace_id再利用を拒否する。"""
    store = InMemorySpaceBindingStore()
    await store.put(_binding(provider_space_ref=ExternalRef("1"), space_id=SpaceId("space-1")))

    with pytest.raises(SpaceBindingStoreError, match="space_id conflict"):
        await store.put(_binding(provider_space_ref=ExternalRef("2"), space_id=SpaceId("space-1")))


@pytest.mark.anyio
async def test_provider_and_provider_space_ref_are_separate_key_parts() -> None:
    """providerとprovider_space_refの組み合わせをkeyとして扱う。"""
    store = InMemorySpaceBindingStore()
    discord = _binding(
        provider="discord",
        provider_space_ref=ExternalRef("same"),
        space_id=SpaceId("space-d"),
    )
    cli = _binding(
        provider="cli",
        provider_space_ref=ExternalRef("same"),
        space_id=SpaceId("space-c"),
    )
    other_ref = _binding(
        provider="discord",
        provider_space_ref=ExternalRef("other"),
        space_id=SpaceId("space-o"),
    )

    await store.put(discord)
    await store.put(cli)
    await store.put(other_ref)

    assert (
        await store.get_by_external_ref(provider="discord", provider_space_ref=ExternalRef("same"))
        == discord
    )
    assert (
        await store.get_by_external_ref(provider="cli", provider_space_ref=ExternalRef("same"))
        == cli
    )
    assert (
        await store.get_by_external_ref(provider="discord", provider_space_ref=ExternalRef("other"))
        == other_ref
    )


@pytest.mark.anyio
async def test_metadata_and_space_kind_round_trip() -> None:
    """metadataとSpaceKindが保持される。"""
    store = InMemorySpaceBindingStore()
    binding = _binding(space_kind=SpaceKind.THREAD, metadata={"thread": "yes"})

    await store.put(binding)
    result = await store.get_by_external_ref(
        provider="discord",
        provider_space_ref=ExternalRef("1"),
    )

    assert result is not None
    assert result.space_kind is SpaceKind.THREAD
    assert result.metadata == {"thread": "yes"}


def _binding(
    *,
    provider: str = "discord",
    provider_space_ref: ExternalRef | None = None,
    space_id: SpaceId | None = None,
    display_name: str = "General",
    space_kind: SpaceKind = SpaceKind.CHANNEL,
    metadata: dict[str, str] | None = None,
) -> SpaceBinding:
    return SpaceBinding(
        space_id=space_id or SpaceId("space-1"),
        provider=provider,
        provider_space_ref=provider_space_ref or ExternalRef("1"),
        display_name=display_name,
        space_kind=space_kind,
        metadata=metadata or {},
    )
