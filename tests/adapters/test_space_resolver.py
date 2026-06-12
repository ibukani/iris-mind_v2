"""SpaceResolver implementation tests."""

from __future__ import annotations

import pytest

from iris.adapters.app_gateway.space_resolver import EphemeralSpaceResolver
from iris.contracts.external_refs import ExternalSpaceRef
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.spaces import SpaceKind
from iris.core.ids import ActorId, ExternalRef


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
async def test_ephemeral_space_resolver_maps_participants() -> None:
    """EphemeralSpaceResolver maps Identity participants into snapshots."""
    resolver = EphemeralSpaceResolver()
    actor = Identity(
        actor_id=ActorId("actor-1"),
        actor_kind=ActorKind.HUMAN,
        display_name="Alice",
        metadata={"key": "val"},
    )

    space = await resolver.resolve_space(
        ExternalSpaceRef(
            provider="discord",
            provider_space_ref=ExternalRef("123"),
            display_name="Channel",
            space_kind=SpaceKind.CHANNEL,
        ),
        participants=[actor],
    )

    assert len(space.participants) == 1
    participant = space.participants[0]
    assert participant.actor_id == ActorId("actor-1")
    assert participant.participant_kind.value == "human"
    assert participant.display_name == "Alice"
    assert participant.identity == actor
    assert participant.metadata == {"key": "val"}
