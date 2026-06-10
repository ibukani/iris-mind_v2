"""Space resolver semantics tests."""

from __future__ import annotations

import pytest

from iris.adapters.app_gateway.space_resolver import SpaceBindingAwareSpaceResolver
from iris.adapters.app_gateway.stable_ids import stable_space_id
from iris.adapters.spaces.memory import InMemorySpaceBindingStore
from iris.contracts.external_refs import ExternalSpaceRef
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.spaces import SpaceBinding, SpaceKind, SpaceParticipantKind
from iris.core.ids import ActorId, ExternalRef, SpaceId


@pytest.mark.anyio
async def test_existing_binding_is_used_when_present() -> None:
    """既存bindingがある場合はbindingのspace_idを使う。"""
    store = InMemorySpaceBindingStore((_binding(metadata={"bound": "yes"}),))
    resolver = SpaceBindingAwareSpaceResolver(binding_store=store)

    space = await resolver.resolve_space(_space_ref(metadata={"incoming": "yes"}))

    assert space.space_id == SpaceId("space-bound")
    assert space.display_name == "Bound Space"


@pytest.mark.anyio
async def test_binding_and_incoming_metadata_are_merged_with_binding_wins() -> None:
    """metadataはincomingにbindingを重ね、衝突時はbindingが勝つ。"""
    store = InMemorySpaceBindingStore((_binding(metadata={"shared": "binding", "bound": "yes"}),))
    resolver = SpaceBindingAwareSpaceResolver(binding_store=store)

    space = await resolver.resolve_space(_space_ref(metadata={"shared": "incoming", "in": "yes"}))

    assert space.metadata == {"shared": "binding", "in": "yes", "bound": "yes"}


@pytest.mark.anyio
async def test_missing_binding_falls_back_to_deterministic_space_id() -> None:
    """bindingがない場合はdeterministic fallback space_idを使う。"""
    resolver = SpaceBindingAwareSpaceResolver(binding_store=InMemorySpaceBindingStore())

    first = await resolver.resolve_space(_space_ref(display_name="One"))
    second = await resolver.resolve_space(_space_ref(display_name="Renamed"))

    expected = stable_space_id("discord", ExternalRef("channel-1"))
    assert first.space_id == expected
    assert second.space_id == expected


@pytest.mark.anyio
async def test_participants_are_mapped_into_space_participants() -> None:
    """Identity participants are mapped into SpaceParticipant entries."""
    resolver = SpaceBindingAwareSpaceResolver()

    space = await resolver.resolve_space(
        _space_ref(),
        participants=(
            Identity(
                actor_id=ActorId("actor-1"),
                actor_kind=ActorKind.HUMAN,
                display_name="Mina",
            ),
        ),
    )

    assert len(space.participants) == 1
    participant = space.participants[0]
    assert participant.actor_id == ActorId("actor-1")
    assert participant.participant_kind is SpaceParticipantKind.HUMAN
    assert participant.display_name == "Mina"


@pytest.mark.anyio
async def test_resolver_works_without_binding_store() -> None:
    """Binding storeなしでもfallback spaceとして解決できる。"""
    resolver = SpaceBindingAwareSpaceResolver()

    space = await resolver.resolve_space(_space_ref())

    assert space.space_id == stable_space_id("discord", ExternalRef("channel-1"))


def _space_ref(
    *,
    display_name: str = "Incoming Space",
    metadata: dict[str, str] | None = None,
) -> ExternalSpaceRef:
    return ExternalSpaceRef(
        provider="discord",
        provider_space_ref=ExternalRef("channel-1"),
        display_name=display_name,
        space_kind=SpaceKind.CHANNEL,
        metadata=metadata or {},
    )


def _binding(*, metadata: dict[str, str] | None = None) -> SpaceBinding:
    return SpaceBinding(
        space_id=SpaceId("space-bound"),
        provider="discord",
        provider_space_ref=ExternalRef("channel-1"),
        display_name="Bound Space",
        space_kind=SpaceKind.CHANNEL,
        metadata=metadata or {},
    )
