"""activity runtime state store。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, override

if TYPE_CHECKING:
    from iris.contracts.activity import ActivityRecord
    from iris.core.ids import ActivityId, ActorId, SpaceId


class ActivityStore(Protocol):
    """受理済みactivity recordを保持するruntime port。"""

    async def record_activity(self, record: ActivityRecord) -> None:
        """Activity recordを保存する。"""
        ...

    async def get_by_id(self, activity_id: ActivityId) -> ActivityRecord | None:
        """Activity IDでrecordを取得する。"""
        ...

    async def latest_for_actor(self, actor_id: ActorId) -> ActivityRecord | None:
        """actorの最新activityを取得する。"""
        ...

    async def latest_for_space(self, space_id: SpaceId) -> ActivityRecord | None:
        """spaceの最新activityを取得する。"""
        ...

    async def has_seen_provider_event(
        self,
        *,
        source: str,
        provider_event_id: str,
    ) -> bool:
        """Provider eventが既に保存済みか返す。"""
        ...


class InMemoryActivityStore(ActivityStore):
    """process内でactivity recordを保持するstore。"""

    def __init__(self) -> None:
        """空のstoreを初期化する。"""
        self._records_by_id: dict[ActivityId, ActivityRecord] = {}
        self._latest_by_actor: dict[ActorId, ActivityRecord] = {}
        self._latest_by_space: dict[SpaceId, ActivityRecord] = {}
        self._provider_events: set[tuple[str, str]] = set()

    @override
    async def record_activity(self, record: ActivityRecord) -> None:
        """未処理のprovider eventまたはID recordを保存する。"""
        provider_key = self._provider_key(record)
        if provider_key is not None and provider_key in self._provider_events:
            return

        self._records_by_id[record.activity_id] = record
        if record.actor_id is not None:
            self._latest_by_actor[record.actor_id] = record
        if record.space_id is not None:
            self._latest_by_space[record.space_id] = record
        if provider_key is not None:
            self._provider_events.add(provider_key)

    @override
    async def get_by_id(self, activity_id: ActivityId) -> ActivityRecord | None:
        """Activity IDでrecordを取得する。

        Returns:
            対応するrecord。未保存の場合はNone。
        """
        return self._records_by_id.get(activity_id)

    @override
    async def latest_for_actor(self, actor_id: ActorId) -> ActivityRecord | None:
        """Actorの最新activityを取得する。

        Returns:
            最新record。未保存の場合はNone。
        """
        return self._latest_by_actor.get(actor_id)

    @override
    async def latest_for_space(self, space_id: SpaceId) -> ActivityRecord | None:
        """Spaceの最新activityを取得する。

        Returns:
            最新record。未保存の場合はNone。
        """
        return self._latest_by_space.get(space_id)

    @override
    async def has_seen_provider_event(
        self,
        *,
        source: str,
        provider_event_id: str,
    ) -> bool:
        """Provider eventが既に保存済みか返す。

        Returns:
            保存済みの場合はTrue。
        """
        return (source, provider_event_id) in self._provider_events

    @staticmethod
    def _provider_key(record: ActivityRecord) -> tuple[str, str] | None:
        if record.source is None or record.provider_event_id is None:
            return None
        return (record.source, record.provider_event_id)
