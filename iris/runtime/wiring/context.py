"""WorkspaceContextAssembler の配線関数。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from iris.runtime.state.availability import AvailabilityResolver
from iris.runtime.state.workspace_assembler import WorkspaceContextAssembler

if TYPE_CHECKING:
    from collections.abc import Callable

    from iris.runtime.state.activity_projection import ActivityProjectionStore
    from iris.runtime.state.presence import PresenceStore
    from iris.runtime.state.space_occupancy import SpaceOccupancyStore


def wire_workspace_context_assembler(
    *,
    activity_projection_store: ActivityProjectionStore | None = None,
    presence_store: PresenceStore | None = None,
    occupancy_store: SpaceOccupancyStore | None = None,
    availability_resolver: AvailabilityResolver | None = None,
    now: Callable[[], datetime] | None = None,
) -> WorkspaceContextAssembler:
    """ランタイムストアから WorkspaceContextAssembler を組み立てる。

    Args:
        activity_projection_store: 任意の activity projection store。
        presence_store: 任意の presence store。
        occupancy_store: 任意の space occupancy store。
        availability_resolver: 任意の resolver。省略時はデフォルトを作成する。
        now: 現在時刻を返す callable。省略時は UTC now を使う。

    Returns:
        WorkspaceContextAssembler: 構成済みの assembler。
    """
    if availability_resolver is None:
        availability_resolver = AvailabilityResolver()
    if now is None:
        now = _utc_now
    return WorkspaceContextAssembler(
        activity_projection_store=activity_projection_store,
        presence_store=presence_store,
        occupancy_store=occupancy_store,
        availability_resolver=availability_resolver,
        now=now,
    )


def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(UTC)
