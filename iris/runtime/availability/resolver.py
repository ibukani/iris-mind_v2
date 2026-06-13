"""受理済みランタイム状態から availability を導出する。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from iris.contracts.availability import AvailabilitySnapshot, AvailabilityStatus
from iris.contracts.presence import PresenceStatus

if TYPE_CHECKING:
    from iris.contracts.activity import ActivityEventRecord
    from iris.contracts.presence import PresenceSnapshot
    from iris.contracts.space_occupancy import SpaceOccupancySnapshot
    from iris.core.ids import ActorId


@dataclass(frozen=True)
class AvailabilityResolver:
    """activity / presence / occupancy スナップショットから availability を導出する。"""

    recent_activity_window_seconds: float = 300.0

    def derive(
        self,
        *,
        actor_id: ActorId | None,
        latest_activity: ActivityEventRecord | None,
        presence: PresenceSnapshot | None,
        space_occupancy: SpaceOccupancySnapshot | None,
        now: datetime,
    ) -> AvailabilitySnapshot:
        """与えられたランタイムスナップショットから availability を導出する。

        Args:
            actor_id: 対象アクター ID。
            latest_activity: 直近の activity event。
            presence: 直近の presence snapshot。
            space_occupancy: 直近の space occupancy snapshot。
            now: 導出時点の時刻。

        Returns:
            AvailabilitySnapshot: 導出結果。
        """
        _ = space_occupancy
        recent = _is_recent_activity(
            latest_activity,
            now=now,
            window_seconds=self.recent_activity_window_seconds,
        )

        status = AvailabilityStatus.UNKNOWN
        reason = "no presence signal and no recent activity"
        observed_at: datetime | None = None
        confidence = 0.3

        if presence is not None:
            observed_at = presence.observed_at
            status, reason, confidence = _derive_from_presence(
                presence.status,
                recent=recent,
            )
        elif recent:
            observed_at = latest_activity.occurred_at if latest_activity is not None else None
            status = AvailabilityStatus.INTERRUPTIBLE
            reason = "no presence signal, but recent activity observed"
            confidence = 0.6

        return AvailabilitySnapshot(
            actor_id=actor_id,
            status=status,
            reason=reason,
            observed_at=observed_at,
            computed_at=now,
            confidence=confidence,
        )


def _derive_from_presence(
    status: PresenceStatus,
    *,
    recent: bool,
) -> tuple[AvailabilityStatus, str, float]:
    """Presence status と直近 activity 有無から availability 属性を導出する。

    Returns:
        tuple[AvailabilityStatus, str, float]: 導出された status / reason / confidence。
    """
    derived_status = AvailabilityStatus.UNKNOWN
    reason = f"unrecognized presence status {status.value}"
    confidence = 0.3

    if status is PresenceStatus.OFFLINE:
        derived_status = AvailabilityStatus.UNAVAILABLE
        reason = "presence is offline"
        confidence = 1.0
    elif status is PresenceStatus.DO_NOT_DISTURB:
        derived_status = AvailabilityStatus.BUSY
        reason = "presence is do-not-disturb"
        confidence = 1.0
    elif status is PresenceStatus.INVISIBLE:
        derived_status = AvailabilityStatus.UNKNOWN
        reason = "presence is invisible"
        confidence = 0.5
    elif status in {PresenceStatus.AWAY, PresenceStatus.IDLE}:
        derived_status = AvailabilityStatus.PASSIVE
        reason = f"presence is {status.value}"
        confidence = 0.8
    elif status is PresenceStatus.ONLINE:
        if recent:
            derived_status = AvailabilityStatus.AVAILABLE
            reason = "online with recent activity"
            confidence = 0.9
        else:
            derived_status = AvailabilityStatus.INTERRUPTIBLE
            reason = "online but no recent activity"
            confidence = 0.7

    return derived_status, reason, confidence


def _is_recent_activity(
    activity: ActivityEventRecord | None,
    *,
    now: datetime,
    window_seconds: float,
) -> bool:
    """Activity event が window 内にあるか判定する。

    Args:
        activity: 判定対象の activity event。
        now: 判定基準時刻。
        window_seconds: 直近とみなす秒数。

    Returns:
        bool: window 内なら True。
    """
    if activity is None:
        return False
    return now - activity.occurred_at <= timedelta(seconds=window_seconds)
