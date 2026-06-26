"""latest activity projection store。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, override

if TYPE_CHECKING:
    from iris.contracts.activity import ActivityEventRecord
    from iris.core.ids import ActorId


class ActivityProjectionStore(Protocol):
    """latest activity projectionを保持するruntime port。"""

    async def update_latest(self, event: ActivityEventRecord) -> None:
        """Accepted activity eventからprojectionを更新する。"""
        ...

    async def latest_for_actor(
        self,
        actor_id: ActorId,
    ) -> ActivityEventRecord | None:
        """actorの最新activity eventを取得する。"""
        ...


class InMemoryActivityProjectionStore(ActivityProjectionStore):
    """process内でlatest activity projectionを保持するstore。"""

    def __init__(self) -> None:
        """空のprojection storeを初期化する。"""
        self._latest_by_actor: dict[ActorId, ActivityEventRecord] = {}

    @override
    async def update_latest(self, event: ActivityEventRecord) -> None:
        """Actor projectionをeventから更新する。"""
        if event.actor_id is not None:
            self._latest_by_actor[event.actor_id] = event

    @override
    async def latest_for_actor(
        self,
        actor_id: ActorId,
    ) -> ActivityEventRecord | None:
        """actorの最新activity eventを取得する。

        Returns:
            最新event。未保存の場合はNone。
        """
        return self._latest_by_actor.get(actor_id)
