"""presence store tests。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from iris.contracts.presence import PresenceSnapshot, PresenceStatus
from iris.core.ids import ActorId
from iris.runtime.state.presence import InMemoryPresenceStore

_NOW = datetime(2026, 6, 13, tzinfo=UTC)


@pytest.mark.anyio
async def test_presence_store_returns_latest_unexpired_snapshot() -> None:
    """actorの最新かつ期限内presenceを返すことを確認する。"""
    store = InMemoryPresenceStore()
    snapshot = _snapshot(PresenceStatus.UNKNOWN)

    await store.update_presence(snapshot)

    assert await store.get_presence_for_actor(ActorId("actor-1"), now=_NOW) == snapshot


@pytest.mark.anyio
async def test_presence_store_hides_expired_snapshot() -> None:
    """期限切れpresenceをcurrent presenceとして返さないことを確認する。"""
    store = InMemoryPresenceStore()
    await store.update_presence(
        _snapshot(PresenceStatus.AWAY, expires_at=_NOW - timedelta(seconds=1))
    )

    assert await store.get_presence_for_actor(ActorId("actor-1"), now=_NOW) is None


@pytest.mark.anyio
async def test_presence_store_ignores_snapshot_without_actor() -> None:
    """Actor IDなしsnapshotを保存しないことを確認する。"""
    store = InMemoryPresenceStore()
    await store.update_presence(
        PresenceSnapshot(
            actor_id=None,
            account_id=None,
            device_id=None,
            source="internal",
            status=PresenceStatus.ONLINE,
            observed_at=_NOW,
            received_at=_NOW,
        )
    )

    assert await store.get_presence_for_actor(ActorId("actor-1"), now=_NOW) is None


def _snapshot(
    status: PresenceStatus,
    *,
    expires_at: datetime | None = None,
) -> PresenceSnapshot:
    return PresenceSnapshot(
        actor_id=ActorId("actor-1"),
        account_id=None,
        device_id=None,
        source="internal",
        status=status,
        observed_at=_NOW,
        received_at=_NOW,
        expires_at=expires_at,
    )
