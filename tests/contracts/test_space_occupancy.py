"""space occupancy contract tests。"""

from __future__ import annotations

from datetime import UTC, datetime

from iris.contracts.space_occupancy import SpaceOccupancySnapshot, SpaceOccupant
from iris.core.ids import ActorId, SpaceId
from tests.helpers.immutability import assert_frozen_field


def test_space_occupant_is_immutable_and_copies_metadata() -> None:
    """SpaceOccupantがimmutable accepted stateであることを確認する。"""
    metadata = {"voice_state": "connected"}
    occupant = _occupant(metadata=metadata)

    metadata["voice_state"] = "disconnected"

    assert occupant.metadata == {"voice_state": "connected"}
    assert_frozen_field(occupant, "expires_at", datetime(2026, 6, 14, tzinfo=UTC))


def test_space_occupancy_snapshot_uses_tuple_occupants() -> None:
    """SpaceOccupancySnapshotがtuple occupantsを保持することを確認する。"""
    occupants = (_occupant(),)
    snapshot = SpaceOccupancySnapshot(
        space_id=SpaceId("space-1"),
        occupants=occupants,
        updated_at=datetime(2026, 6, 13, tzinfo=UTC),
    )

    assert snapshot.occupants == occupants
    assert isinstance(snapshot.occupants, tuple)


def _occupant(
    *,
    metadata: dict[str, str] | None = None,
) -> SpaceOccupant:
    return SpaceOccupant(
        actor_id=ActorId("actor-1"),
        joined_at=datetime(2026, 6, 13, tzinfo=UTC),
        last_seen_at=datetime(2026, 6, 13, 0, 0, 1, tzinfo=UTC),
        metadata=metadata or {},
    )
