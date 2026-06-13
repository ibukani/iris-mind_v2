"""AvailabilityResolver tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from iris.contracts.activity import ActivityEventRecord, ActivityKind
from iris.contracts.availability import AvailabilityStatus
from iris.contracts.presence import PresenceSnapshot, PresenceStatus
from iris.contracts.space_occupancy import SpaceOccupancySnapshot, SpaceOccupant
from iris.core.ids import ActivityId, ActorId, ObservationId, SpaceId
from iris.runtime.availability.resolver import AvailabilityResolver


@pytest.fixture
def actor_id() -> ActorId:
    """Default actor id for resolver tests.

    Returns:
        ActorId: test actor id.
    """
    return ActorId("actor-resolver")


@pytest.fixture
def now() -> datetime:
    """Default current time for resolver tests.

    Returns:
        datetime: fixed current time.
    """
    return datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def resolver() -> AvailabilityResolver:
    """Default resolver with a short window for deterministic tests.

    Returns:
        AvailabilityResolver: configured resolver.
    """
    return AvailabilityResolver(recent_activity_window_seconds=60.0)


def _recent_activity(now: datetime) -> ActivityEventRecord:
    """Return an activity event inside the default window.

    Returns:
        ActivityEventRecord: recent activity event.
    """
    return ActivityEventRecord(
        activity_id=ActivityId("activity-recent"),
        observation_id=ObservationId("obs-recent"),
        provider_event_id=None,
        provider_sequence=None,
        actor_id=ActorId("actor-resolver"),
        account_id=None,
        device_id=None,
        space_id=None,
        source=None,
        kind=ActivityKind.APP_OPENED,
        occurred_at=now - timedelta(seconds=30),
        received_at=now,
    )


def _stale_activity(now: datetime) -> ActivityEventRecord:
    """Return an activity event outside the default window.

    Returns:
        ActivityEventRecord: stale activity event.
    """
    return ActivityEventRecord(
        activity_id=ActivityId("activity-stale"),
        observation_id=ObservationId("obs-stale"),
        provider_event_id=None,
        provider_sequence=None,
        actor_id=ActorId("actor-resolver"),
        account_id=None,
        device_id=None,
        space_id=None,
        source=None,
        kind=ActivityKind.APP_CLOSED,
        occurred_at=now - timedelta(seconds=120),
        received_at=now,
    )


def _presence(
    status: PresenceStatus,
    *,
    now: datetime,
) -> PresenceSnapshot:
    """Return a presence snapshot with the given status.

    Returns:
        PresenceSnapshot: configured presence snapshot.
    """
    return PresenceSnapshot(
        actor_id=ActorId("actor-resolver"),
        account_id=None,
        device_id=None,
        source=None,
        status=status,
        observed_at=now - timedelta(seconds=5),
        received_at=now,
    )


def test_online_with_recent_activity_is_available(
    resolver: AvailabilityResolver,
    actor_id: ActorId,
    now: datetime,
) -> None:
    """ONLINE + 直近 activity なら available と判定する。"""
    snapshot = resolver.derive(
        actor_id=actor_id,
        latest_activity=_recent_activity(now),
        presence=_presence(PresenceStatus.ONLINE, now=now),
        space_occupancy=None,
        now=now,
    )

    assert snapshot.status is AvailabilityStatus.AVAILABLE
    assert snapshot.confidence == 0.9  # noqa: RUF069 -- exact float literal comparison in tests
    assert "recent activity" in snapshot.reason


def test_online_without_recent_activity_is_interruptible(
    resolver: AvailabilityResolver,
    actor_id: ActorId,
    now: datetime,
) -> None:
    """ONLINE だが直近 activity がない場合は interruptible と判定する。"""
    snapshot = resolver.derive(
        actor_id=actor_id,
        latest_activity=_stale_activity(now),
        presence=_presence(PresenceStatus.ONLINE, now=now),
        space_occupancy=None,
        now=now,
    )

    assert snapshot.status is AvailabilityStatus.INTERRUPTIBLE
    assert snapshot.confidence == 0.7  # noqa: RUF069 -- exact float literal comparison in tests


def test_offline_is_unavailable(
    resolver: AvailabilityResolver,
    actor_id: ActorId,
    now: datetime,
) -> None:
    """OFFLINE なら unavailable と判定する。"""
    snapshot = resolver.derive(
        actor_id=actor_id,
        latest_activity=None,
        presence=_presence(PresenceStatus.OFFLINE, now=now),
        space_occupancy=None,
        now=now,
    )

    assert snapshot.status is AvailabilityStatus.UNAVAILABLE
    assert snapshot.confidence == 1.0  # noqa: RUF069 -- exact float literal comparison in tests


def test_do_not_disturb_is_busy(
    resolver: AvailabilityResolver,
    actor_id: ActorId,
    now: datetime,
) -> None:
    """DO_NOT_DISTURB なら busy と判定する。"""
    snapshot = resolver.derive(
        actor_id=actor_id,
        latest_activity=None,
        presence=_presence(PresenceStatus.DO_NOT_DISTURB, now=now),
        space_occupancy=None,
        now=now,
    )

    assert snapshot.status is AvailabilityStatus.BUSY
    assert snapshot.confidence == 1.0  # noqa: RUF069 -- exact float literal comparison in tests


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (PresenceStatus.AWAY, AvailabilityStatus.PASSIVE),
        (PresenceStatus.IDLE, AvailabilityStatus.PASSIVE),
    ],
)
def test_away_and_idle_are_passive(
    resolver: AvailabilityResolver,
    actor_id: ActorId,
    now: datetime,
    status: PresenceStatus,
    expected: AvailabilityStatus,
) -> None:
    """AWAY / IDLE なら passive と判定する。"""
    snapshot = resolver.derive(
        actor_id=actor_id,
        latest_activity=None,
        presence=_presence(status, now=now),
        space_occupancy=None,
        now=now,
    )

    assert snapshot.status is expected
    assert snapshot.confidence == 0.8  # noqa: RUF069 -- exact float literal comparison in tests


def test_invisible_is_unknown(
    resolver: AvailabilityResolver,
    actor_id: ActorId,
    now: datetime,
) -> None:
    """INVISIBLE なら unknown と判定する。"""
    snapshot = resolver.derive(
        actor_id=actor_id,
        latest_activity=None,
        presence=_presence(PresenceStatus.INVISIBLE, now=now),
        space_occupancy=None,
        now=now,
    )

    assert snapshot.status is AvailabilityStatus.UNKNOWN
    assert snapshot.confidence == 0.5  # noqa: RUF069 -- exact float literal comparison in tests


def test_no_presence_with_recent_activity_is_interruptible(
    resolver: AvailabilityResolver,
    actor_id: ActorId,
    now: datetime,
) -> None:
    """Presence 信号がなくても直近 activity があれば interruptible と判定する。"""
    snapshot = resolver.derive(
        actor_id=actor_id,
        latest_activity=_recent_activity(now),
        presence=None,
        space_occupancy=None,
        now=now,
    )

    assert snapshot.status is AvailabilityStatus.INTERRUPTIBLE
    assert snapshot.confidence == 0.6  # noqa: RUF069 -- exact float literal comparison in tests


def test_no_presence_and_no_activity_is_unknown(
    resolver: AvailabilityResolver,
    actor_id: ActorId,
    now: datetime,
) -> None:
    """Presence も activity もなければ unknown と判定する。"""
    snapshot = resolver.derive(
        actor_id=actor_id,
        latest_activity=None,
        presence=None,
        space_occupancy=None,
        now=now,
    )

    assert snapshot.status is AvailabilityStatus.UNKNOWN
    assert snapshot.confidence == 0.3  # noqa: RUF069 -- exact float literal comparison in tests


def test_observed_at_comes_from_presence(
    resolver: AvailabilityResolver,
    actor_id: ActorId,
    now: datetime,
) -> None:
    """observed_at は presence の観測時刻を引き継ぐ。"""
    presence = _presence(PresenceStatus.ONLINE, now=now)
    snapshot = resolver.derive(
        actor_id=actor_id,
        latest_activity=None,
        presence=presence,
        space_occupancy=None,
        now=now,
    )

    assert snapshot.observed_at == presence.observed_at


def test_space_occupancy_is_ignored_for_now(
    resolver: AvailabilityResolver,
    actor_id: ActorId,
    now: datetime,
) -> None:
    """現時点では space_occupancy は availability 判定に使われない。"""
    occupancy = SpaceOccupancySnapshot(
        space_id=SpaceId("space-1"),
        occupants=(
            SpaceOccupant(
                actor_id=ActorId("other"),
                account_id=None,
                device_id=None,
                joined_at=now,
                last_seen_at=now,
                expires_at=None,
            ),
        ),
        updated_at=now,
    )
    snapshot = resolver.derive(
        actor_id=actor_id,
        latest_activity=None,
        presence=_presence(PresenceStatus.ONLINE, now=now),
        space_occupancy=occupancy,
        now=now,
    )

    assert snapshot.status is AvailabilityStatus.INTERRUPTIBLE


def test_actor_id_is_preserved(
    resolver: AvailabilityResolver,
    actor_id: ActorId,
    now: datetime,
) -> None:
    """actor_id は snapshot に保持される。"""
    snapshot = resolver.derive(
        actor_id=actor_id,
        latest_activity=None,
        presence=None,
        space_occupancy=None,
        now=now,
    )

    assert snapshot.actor_id == actor_id
