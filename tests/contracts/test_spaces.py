"""相互作用スペース契約のテスト。"""

from __future__ import annotations

from types import MappingProxyType

from iris.contracts.identity import ActorKind, Identity
from iris.contracts.spaces import (
    InteractionSpace,
    SpaceKind,
    SpaceParticipant,
    SpaceParticipantKind,
)
from iris.core.ids import ActorId, ExternalRef, SpaceId
from tests.helpers.immutability import assert_frozen_field


def test_space_kind_enum_exposes_required_values() -> None:
    """SpaceKind must expose direct_message, channel, thread, room, broadcast."""
    assert {kind.value for kind in SpaceKind} == {
        "direct_message",
        "channel",
        "thread",
        "room",
        "broadcast",
    }


def test_space_participant_kind_enum_exposes_required_values() -> None:
    """SpaceParticipantKind must mirror the actor kinds plus its own enum name."""
    assert {kind.value for kind in SpaceParticipantKind} == {
        "human",
        "device",
        "service",
        "system",
        "iris",
    }


def test_interaction_space_is_frozen_and_typed() -> None:
    """InteractionSpace is a frozen dataclass with typed fields and empty defaults."""
    space = InteractionSpace(
        space_id=SpaceId("space-1"),
        space_kind=SpaceKind.CHANNEL,
        display_name="general",
    )

    assert space.space_id == SpaceId("space-1")
    assert space.space_kind is SpaceKind.CHANNEL
    assert space.display_name == "general"
    assert space.participants == ()
    assert space.metadata == MappingProxyType({})

    assert_frozen_field(space, "display_name", "renamed")


def test_space_participant_is_frozen_and_typed() -> None:
    """SpaceParticipant is a frozen dataclass with typed fields and empty defaults."""
    participant = SpaceParticipant(
        actor_id=ActorId("actor-1"),
        participant_kind=SpaceParticipantKind.HUMAN,
        display_name="Mina",
    )

    assert participant.actor_id == ActorId("actor-1")
    assert participant.participant_kind is SpaceParticipantKind.HUMAN
    assert participant.display_name == "Mina"
    assert participant.identity is None
    assert participant.metadata == MappingProxyType({})

    assert_frozen_field(participant, "display_name", "Other")


def test_interaction_space_carries_participants_and_metadata() -> None:
    """InteractionSpace exposes a tuple of participants and a metadata mapping."""
    identity = Identity(
        actor_id=ActorId("actor-iris"),
        actor_kind=ActorKind.IRIS,
        display_name="Iris",
        provider="iris",
        provider_subject=ExternalRef("iris-core"),
    )
    participants = (
        SpaceParticipant(
            actor_id=ActorId("actor-1"),
            participant_kind=SpaceParticipantKind.HUMAN,
            display_name="Mina",
        ),
        SpaceParticipant(
            actor_id=ActorId("actor-iris"),
            participant_kind=SpaceParticipantKind.IRIS,
            display_name="Iris",
            identity=identity,
        ),
    )
    metadata = MappingProxyType({"topic": "tea"})

    space = InteractionSpace(
        space_id=SpaceId("space-1"),
        space_kind=SpaceKind.DIRECT_MESSAGE,
        display_name="DM",
        participants=participants,
        metadata=metadata,
    )

    assert space.participants == participants
    assert space.metadata is metadata
    assert space.participants[1].identity is identity


def test_interaction_space_rejects_mutation_of_participants() -> None:
    """InteractionSpace.participants is a tuple and rejects in-place mutation."""
    space = InteractionSpace(
        space_id=SpaceId("space-1"),
        space_kind=SpaceKind.ROOM,
        display_name="room",
        participants=(
            SpaceParticipant(
                actor_id=ActorId("actor-1"),
                participant_kind=SpaceParticipantKind.HUMAN,
                display_name="Mina",
            ),
        ),
    )

    assert isinstance(space.participants, tuple)
    assert getattr(space.participants, "append", None) is None
    assert not hasattr(space.participants, "append")


def test_space_supports_each_kind() -> None:
    """InteractionSpace can be constructed for every SpaceKind value."""
    for kind in SpaceKind:
        space = InteractionSpace(
            space_id=SpaceId(f"space-{kind.value}"),
            space_kind=kind,
            display_name=f"space-{kind.value}",
        )
        assert space.space_kind is kind


def test_space_participant_supports_each_kind() -> None:
    """SpaceParticipant can be constructed for every SpaceParticipantKind value."""
    for kind in SpaceParticipantKind:
        participant = SpaceParticipant(
            actor_id=ActorId(f"actor-{kind.value}"),
            participant_kind=kind,
            display_name=f"display-{kind.value}",
        )
        assert participant.participant_kind is kind
