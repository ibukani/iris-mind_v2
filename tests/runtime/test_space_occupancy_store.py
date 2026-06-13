"""space occupancy store tests。"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from iris.contracts.space_occupancy import SpaceOccupant
from iris.core.ids import ActorId, SpaceId
from iris.runtime.spaces.occupancy_store import InMemorySpaceOccupancyStore

_NOW = datetime(2026, 6, 13, tzinfo=UTC)
_SPACE_ID = SpaceId("space-1")


@pytest.mark.anyio
async def test_actor_joined_adds_and_replaces_occupant() -> None:
    """同じactorのjoinがoccupantを置換することを確認する。"""
    store = InMemorySpaceOccupancyStore()
    first = _occupant()
    replacement = replace(first, last_seen_at=_NOW + timedelta(seconds=2))

    await store.actor_joined(space_id=_SPACE_ID, occupant=first)
    await store.actor_joined(space_id=_SPACE_ID, occupant=replacement)

    snapshot = await store.get_occupancy(_SPACE_ID, now=_NOW)
    assert snapshot.occupants == (replacement,)
    assert snapshot.updated_at == replacement.last_seen_at


@pytest.mark.anyio
async def test_actor_left_is_idempotent() -> None:
    """actor_leftがactorを除去し、再実行しても失敗しないことを確認する。"""
    store = InMemorySpaceOccupancyStore()
    await store.actor_joined(space_id=_SPACE_ID, occupant=_occupant())

    await store.actor_left(space_id=_SPACE_ID, actor_id=ActorId("actor-1"), at=_NOW)
    await store.actor_left(space_id=_SPACE_ID, actor_id=ActorId("actor-1"), at=_NOW)

    snapshot = await store.get_occupancy(_SPACE_ID, now=_NOW)
    assert snapshot.occupants == ()


@pytest.mark.anyio
async def test_get_occupancy_filters_expired_occupants() -> None:
    """期限切れoccupantをsnapshotから除くことを確認する。"""
    store = InMemorySpaceOccupancyStore()
    await store.actor_joined(
        space_id=_SPACE_ID,
        occupant=_occupant(expires_at=_NOW),
    )

    snapshot = await store.get_occupancy(_SPACE_ID, now=_NOW)

    assert snapshot.occupants == ()


@pytest.mark.anyio
async def test_replace_occupancy_replaces_full_actor_set() -> None:
    """replace_occupancyがspaceの全occupantを置換することを確認する。"""
    store = InMemorySpaceOccupancyStore()
    await store.actor_joined(space_id=_SPACE_ID, occupant=_occupant())
    replacement = replace(_occupant(), actor_id=ActorId("actor-2"))

    await store.replace_occupancy(
        space_id=_SPACE_ID,
        occupants=(replacement,),
        at=_NOW + timedelta(seconds=3),
    )

    snapshot = await store.get_occupancy(_SPACE_ID, now=_NOW)
    assert snapshot.occupants == (replacement,)
    assert snapshot.updated_at == _NOW + timedelta(seconds=3)


def _occupant(*, expires_at: datetime | None = None) -> SpaceOccupant:
    return SpaceOccupant(
        actor_id=ActorId("actor-1"),
        joined_at=_NOW - timedelta(seconds=1),
        last_seen_at=_NOW,
        expires_at=expires_at,
    )
