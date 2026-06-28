"""ワークスペースで共有される最小限のコンテキスト型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from iris.contracts.activity import ActivityEventRecord
from iris.contracts.availability import AvailabilitySnapshot
from iris.contracts.identity import Identity
from iris.contracts.presence import PresenceSnapshot
from iris.contracts.space_occupancy import SpaceOccupancySnapshot
from iris.contracts.spaces import InteractionSpace
from iris.core.ids import AccountId, ActorId, DeviceId, SpaceId


class ActorContextSnapshot(BaseModel):
    """1 ターンで参照可能なアクター・アカウント・デバイスコンテキスト。"""

    model_config = ConfigDict(frozen=True)

    actor: Identity | None = None
    account_id: AccountId | None = None
    device_id: DeviceId | None = None


class SpaceContextSnapshot(BaseModel):
    """1 ターンで参照可能なスペースコンテキスト。"""

    model_config = ConfigDict(frozen=True)

    space_id: SpaceId | None = None
    space: InteractionSpace | None = None
    participant_actor_ids: tuple[ActorId, ...] = ()


class SituationContextSnapshot(BaseModel):
    """現在の認知ターン向けに、ランタイム状態から組み立てられた状況スナップショット。"""

    model_config = ConfigDict(frozen=True)

    latest_activity: ActivityEventRecord | None = None
    presence: PresenceSnapshot | None = None
    space_occupancy: SpaceOccupancySnapshot | None = None
    availability: AvailabilitySnapshot | None = None
