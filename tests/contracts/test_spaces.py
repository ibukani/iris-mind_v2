"""Tests for Spaces contracts."""
from __future__ import annotations

import pytest

from iris.contracts.spaces import (
    InteractionSpace,
    SpaceBinding,
    SpaceKind,
    SpaceParticipant,
    SpaceParticipantKind,
)
from iris.core.ids import ActorId, ExternalRef, SpaceId


def test_space_participant_metadata_is_defensively_copied() -> None:
    """SpaceParticipant defensively copies metadata."""
    metadata = {"role": "admin"}
    participant = SpaceParticipant(
        actor_id=ActorId("act-1"),
        participant_kind=SpaceParticipantKind.HUMAN,
        display_name="User",
        metadata=metadata,
    )

    metadata["role"] = "user"

    assert participant.metadata["role"] == "admin"
    with pytest.raises(TypeError):
        participant.metadata["new"] = "value"  # type: ignore[index]  # testing immutability


def test_interaction_space_metadata_is_defensively_copied() -> None:
    """InteractionSpace defensively copies metadata."""
    metadata = {"topic": "general"}
    space = InteractionSpace(
        space_id=SpaceId("spc-1"),
        space_kind=SpaceKind.CHANNEL,
        display_name="General",
        metadata=metadata,
    )

    metadata["topic"] = "random"

    assert space.metadata["topic"] == "general"
    with pytest.raises(TypeError):
        space.metadata["new"] = "value"  # type: ignore[index]  # testing immutability


def test_space_binding_metadata_is_defensively_copied() -> None:
    """SpaceBinding defensively copies metadata."""
    metadata = {"region": "us-east"}
    binding = SpaceBinding(
        provider="discord",
        provider_space_ref=ExternalRef("123"),
        space_id=SpaceId("spc-1"),
        display_name="Server",
        space_kind=SpaceKind.CHANNEL,
        metadata=metadata,
    )

    metadata["region"] = "us-west"

    assert binding.metadata["region"] == "us-east"
    with pytest.raises(TypeError):
        binding.metadata["new"] = "value"  # type: ignore[index]  # testing immutability
