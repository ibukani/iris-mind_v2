"""Tests for Spaces contracts."""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, cast

import pytest

from iris.contracts.spaces import (
    InteractionSpace,
    SpaceBinding,
    SpaceKind,
)
from iris.core.ids import ExternalRef, SpaceId
from tests.helpers.immutability import assert_frozen_field

if TYPE_CHECKING:
    from collections.abc import MutableMapping


def test_space_kind_enum_exposes_required_values() -> None:
    """SpaceKindがtext/voice channelを区別することを確認する。"""
    assert {kind.value for kind in SpaceKind} == {
        "direct_message",
        "text_channel",
        "thread",
        "voice_channel",
        "room",
        "broadcast",
    }


def test_interaction_space_is_frozen_and_typed() -> None:
    """InteractionSpace is a frozen dataclass with typed fields and empty defaults."""
    space = InteractionSpace(
        space_id=SpaceId("space-1"),
        space_kind=SpaceKind.TEXT_CHANNEL,
        display_name="general",
    )

    assert space.space_id == SpaceId("space-1")
    assert space.space_kind is SpaceKind.TEXT_CHANNEL
    assert space.display_name == "general"
    assert space.metadata == MappingProxyType({})
    assert not hasattr(space, "participants")

    assert_frozen_field(space, "display_name", "renamed")


def test_interaction_space_carries_stable_context_metadata() -> None:
    """InteractionSpaceが在室者を持たず安定context metadataだけを運ぶことを確認する。"""
    metadata = MappingProxyType({"topic": "tea"})

    space = InteractionSpace(
        space_id=SpaceId("space-1"),
        space_kind=SpaceKind.DIRECT_MESSAGE,
        display_name="DM",
        metadata=metadata,
    )

    assert space.metadata == metadata
    assert not hasattr(space, "participants")


def test_space_supports_each_kind() -> None:
    """InteractionSpace can be constructed for every SpaceKind value."""
    for kind in SpaceKind:
        space = InteractionSpace(
            space_id=SpaceId(f"space-{kind.value}"),
            space_kind=kind,
            display_name=f"space-{kind.value}",
        )
        assert space.space_kind is kind


def test_interaction_space_metadata_is_defensively_copied() -> None:
    """InteractionSpace defensively copies metadata."""
    metadata = {"topic": "general"}
    space = InteractionSpace(
        space_id=SpaceId("space-1"),
        space_kind=SpaceKind.TEXT_CHANNEL,
        display_name="general",
        metadata=metadata,
    )

    metadata["topic"] = "changed"

    assert space.metadata["topic"] == "general"
    with pytest.raises(TypeError):
        cast("MutableMapping[str, str]", space.metadata)["new"] = "value"


def test_space_binding_metadata_is_defensively_copied() -> None:
    """SpaceBinding defensively copies metadata."""
    metadata = {"region": "us-east"}
    binding = SpaceBinding(
        provider="discord",
        provider_space_ref=ExternalRef("guild-1/channel-1"),
        space_id=SpaceId("space-1"),
        display_name="general",
        space_kind=SpaceKind.TEXT_CHANNEL,
        metadata=metadata,
    )

    metadata["region"] = "changed"

    assert binding.metadata["region"] == "us-east"
    with pytest.raises(TypeError):
        cast("MutableMapping[str, str]", binding.metadata)["new"] = "value"
