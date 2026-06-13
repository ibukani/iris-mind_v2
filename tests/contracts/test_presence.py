"""Presence contract tests."""

from __future__ import annotations

from datetime import UTC, datetime

from iris.contracts.presence import PresenceSnapshot, PresenceStatus
from iris.core.ids import ActorId
from tests.helpers.immutability import assert_frozen_field


def test_presence_status_exposes_provider_visible_states() -> None:
    """PresenceStatusがprovider-visible状態を網羅することを確認する。"""
    assert {status.value for status in PresenceStatus} == {
        "unknown",
        "online",
        "offline",
        "away",
        "idle",
        "do_not_disturb",
        "invisible",
    }


def test_presence_snapshot_is_immutable_and_copies_metadata() -> None:
    """PresenceSnapshotがimmutable accepted stateであることを確認する。"""
    metadata = {"raw_provider_state": "active"}
    snapshot = PresenceSnapshot(
        actor_id=ActorId("actor-1"),
        account_id=None,
        device_id=None,
        source="internal",
        status=PresenceStatus.ONLINE,
        observed_at=datetime(2026, 6, 13, tzinfo=UTC),
        received_at=datetime(2026, 6, 13, 0, 0, 1, tzinfo=UTC),
        metadata=metadata,
    )

    metadata["raw_provider_state"] = "idle"

    assert snapshot.metadata == {"raw_provider_state": "active"}
    assert_frozen_field(snapshot, "status", PresenceStatus.OFFLINE)
