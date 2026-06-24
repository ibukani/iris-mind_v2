"""AvailabilityResolver の配線関数。"""

from __future__ import annotations

from iris.runtime.state.availability import AvailabilityResolver


def wire_availability_resolver(
    *,
    recent_activity_window_seconds: float = 300.0,
) -> AvailabilityResolver:
    """標準的な AvailabilityResolver を組み立てる。

    Args:
        recent_activity_window_seconds: 直近 activity とみなす秒数。

    Returns:
        AvailabilityResolver: 構成済みの resolver。
    """
    return AvailabilityResolver(
        recent_activity_window_seconds=recent_activity_window_seconds,
    )
