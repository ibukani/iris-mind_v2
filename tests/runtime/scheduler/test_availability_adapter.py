"""DeliveryAvailabilityResolverAdapter tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, override

import pytest

from iris.contracts.availability import AvailabilityStatus
from iris.contracts.delivery import DeliveryTarget
from iris.contracts.presence import PresenceSnapshot, PresenceStatus
from iris.core.ids import ActorId, ExternalRef, SessionId
from iris.runtime.activity.projections import ActivityProjectionStore
from iris.runtime.availability.resolver import AvailabilityResolver
from iris.runtime.presence.store import PresenceStore
from iris.runtime.scheduler.availability import DeliveryAvailabilityResolverAdapter

if TYPE_CHECKING:
    from iris.contracts.activity import ActivityEventRecord
    from iris.core.ids import SpaceId

pytestmark = pytest.mark.anyio


def _target(actor_id: ActorId | None = None) -> DeliveryTarget:
    """Build a DeliveryTarget for tests.

    Returns:
        構成済みの DeliveryTarget。
    """
    return DeliveryTarget(
        provider="discord",
        provider_subject=ExternalRef("user-1"),
        provider_space_ref=None,
        session_id=SessionId("session-1"),
        actor_id=actor_id,
    )


@dataclass
class _FakePresenceStore(PresenceStore):
    """PresenceStore fake."""

    snapshot: PresenceSnapshot | None

    @override
    async def update_presence(self, snapshot: PresenceSnapshot) -> None:
        """No-op for tests."""

    @override
    async def get_presence_for_actor(
        self,
        actor_id: ActorId,
        *,
        now: datetime,
    ) -> PresenceSnapshot | None:
        """Return configured snapshot.

        Returns:
            設定済みの PresenceSnapshot または None。
        """
        _ = actor_id, now
        return self.snapshot


@dataclass
class _FakeActivityProjectionStore(ActivityProjectionStore):
    """ActivityProjectionStore fake."""

    @override
    async def update_latest(self, event: ActivityEventRecord) -> None:
        """No-op for tests."""

    @override
    async def latest_for_actor(
        self,
        actor_id: ActorId,
    ) -> ActivityEventRecord | None:
        """Return None for tests.

        Returns:
            常に None。
        """
        _ = actor_id
        return None

    @override
    async def latest_for_space(
        self,
        space_id: SpaceId,
    ) -> ActivityEventRecord | None:
        """Return None for tests.

        Returns:
            常に None。
        """
        _ = space_id
        return None


async def test_adapter_returns_none_when_actor_id_is_none() -> None:
    """Adapter returns None when target has no actor_id."""
    adapter = DeliveryAvailabilityResolverAdapter(
        resolver=AvailabilityResolver(),
        presence_store=_FakePresenceStore(snapshot=None),
        activity_projection_store=_FakeActivityProjectionStore(),
    )
    result = await adapter.availability_for_target(
        _target(actor_id=None),
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert result is None


async def test_adapter_returns_snapshot_with_presence() -> None:
    """Adapter derives availability from presence store."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    presence = PresenceSnapshot(
        actor_id=ActorId("actor-1"),
        account_id=None,
        device_id=None,
        source="test",
        status=PresenceStatus.DO_NOT_DISTURB,
        observed_at=now,
        received_at=now,
    )
    adapter = DeliveryAvailabilityResolverAdapter(
        resolver=AvailabilityResolver(),
        presence_store=_FakePresenceStore(snapshot=presence),
        activity_projection_store=_FakeActivityProjectionStore(),
    )
    result = await adapter.availability_for_target(
        _target(actor_id=ActorId("actor-1")),
        now=now,
    )
    assert result is not None
    assert result.status is AvailabilityStatus.BUSY


async def test_adapter_returns_unknown_without_presence() -> None:
    """Adapter returns UNKNOWN when no presence is stored."""
    adapter = DeliveryAvailabilityResolverAdapter(
        resolver=AvailabilityResolver(),
        presence_store=_FakePresenceStore(snapshot=None),
        activity_projection_store=_FakeActivityProjectionStore(),
    )
    result = await adapter.availability_for_target(
        _target(actor_id=ActorId("actor-1")),
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert result is not None
    assert result.status is AvailabilityStatus.UNKNOWN
