"""presence runtime state store。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, override

if TYPE_CHECKING:
    from datetime import datetime

    from iris.contracts.presence import PresenceSnapshot
    from iris.core.ids import ActorId


class PresenceStore(Protocol):
    """受理済みactor presenceを保持するruntime port。"""

    async def update_presence(self, snapshot: PresenceSnapshot) -> None:
        """actorの最新presenceを保存する。"""
        ...

    async def get_presence_for_actor(
        self,
        actor_id: ActorId,
        *,
        now: datetime,
    ) -> PresenceSnapshot | None:
        """期限内の最新actor presenceを取得する。"""
        ...


class InMemoryPresenceStore(PresenceStore):
    """process内で最新actor presenceを保持するstore。"""

    def __init__(self) -> None:
        """空のstoreを初期化する。"""
        self._snapshots_by_actor: dict[ActorId, PresenceSnapshot] = {}

    @override
    async def update_presence(self, snapshot: PresenceSnapshot) -> None:
        """Actor IDがあるsnapshotを最新値として保存する。"""
        if snapshot.actor_id is not None:
            self._snapshots_by_actor[snapshot.actor_id] = snapshot

    @override
    async def get_presence_for_actor(
        self,
        actor_id: ActorId,
        *,
        now: datetime,
    ) -> PresenceSnapshot | None:
        """期限内の最新actor presenceを取得する。

        Returns:
            期限内のsnapshot。未保存または期限切れの場合はNone。
        """
        snapshot = self._snapshots_by_actor.get(actor_id)
        if snapshot is None:
            return None
        if snapshot.expires_at is not None and snapshot.expires_at <= now:
            return None
        return snapshot
