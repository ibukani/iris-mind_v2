"""space occupancy runtime state store。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, override

from iris.contracts.space_occupancy import SpaceOccupancySnapshot

if TYPE_CHECKING:
    from datetime import datetime

    from iris.contracts.space_occupancy import SpaceOccupant
    from iris.core.ids import ActorId, SpaceId


class SpaceOccupancyStore(Protocol):
    """live spaceの受理済みcurrent occupantsを保持するruntime port。"""

    async def actor_joined(
        self,
        *,
        space_id: SpaceId,
        occupant: SpaceOccupant,
    ) -> None:
        """actorをspace occupancyへ追加または置換する。"""
        ...

    async def actor_left(
        self,
        *,
        space_id: SpaceId,
        actor_id: ActorId,
        at: datetime,
    ) -> None:
        """actorをspace occupancyから除去する。"""
        ...

    async def get_occupancy(
        self,
        space_id: SpaceId,
        *,
        now: datetime,
    ) -> SpaceOccupancySnapshot:
        """期限切れoccupantを除いたsnapshotを取得する。"""
        ...

    async def replace_occupancy(
        self,
        *,
        space_id: SpaceId,
        occupants: tuple[SpaceOccupant, ...],
        at: datetime,
    ) -> None:
        """spaceのoccupancy全体を置換する。"""
        ...


class InMemorySpaceOccupancyStore(SpaceOccupancyStore):
    """process内でlive space occupancyを保持するstore。"""

    def __init__(self) -> None:
        """空のstoreを初期化する。"""
        self._occupants_by_space: dict[SpaceId, dict[ActorId, SpaceOccupant]] = {}
        self._updated_at_by_space: dict[SpaceId, datetime] = {}

    @override
    async def actor_joined(
        self,
        *,
        space_id: SpaceId,
        occupant: SpaceOccupant,
    ) -> None:
        """actorをspace occupancyへ追加または置換する。"""
        occupants = self._occupants_by_space.setdefault(space_id, {})
        occupants[occupant.actor_id] = occupant
        self._updated_at_by_space[space_id] = occupant.last_seen_at

    @override
    async def actor_left(
        self,
        *,
        space_id: SpaceId,
        actor_id: ActorId,
        at: datetime,
    ) -> None:
        """actorが存在する場合だけspace occupancyから除去する。"""
        occupants = self._occupants_by_space.get(space_id)
        if occupants is None or actor_id not in occupants:
            return
        del occupants[actor_id]
        self._updated_at_by_space[space_id] = at

    @override
    async def get_occupancy(
        self,
        space_id: SpaceId,
        *,
        now: datetime,
    ) -> SpaceOccupancySnapshot:
        """期限切れoccupantを除いた安定順序のsnapshotを取得する。

        Returns:
            現在有効なoccupantsのsnapshot。
        """
        occupants = self._occupants_by_space.get(space_id, {})
        active_occupants = tuple(
            occupant
            for occupant in occupants.values()
            if occupant.expires_at is None or occupant.expires_at > now
        )
        return SpaceOccupancySnapshot(
            space_id=space_id,
            occupants=active_occupants,
            updated_at=self._updated_at_by_space.get(space_id, now),
        )

    @override
    async def replace_occupancy(
        self,
        *,
        space_id: SpaceId,
        occupants: tuple[SpaceOccupant, ...],
        at: datetime,
    ) -> None:
        """spaceのoccupancy全体をactor ID単位で置換する。"""
        self._occupants_by_space[space_id] = {occupant.actor_id: occupant for occupant in occupants}
        self._updated_at_by_space[space_id] = at
