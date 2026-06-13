"""bounded runtime activity event journal。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, override

if TYPE_CHECKING:
    from iris.contracts.activity import ActivityEventRecord
    from iris.core.ids import ActivityId


class ActivityAppendSkipReason(StrEnum):
    """ActivityJournal.appendがeventを受理しない理由。"""

    DUPLICATE_PROVIDER_EVENT = "duplicate_provider_event"


@dataclass(frozen=True)
class ActivityAppendResult:
    """ActivityJournal.appendの結果。"""

    accepted: bool
    event: ActivityEventRecord | None
    reason: ActivityAppendSkipReason | None = None


class ActivityJournal(Protocol):
    """受理済みactivity eventをbounded journalとして保持するruntime port。"""

    async def append(self, event: ActivityEventRecord) -> ActivityAppendResult:
        """Activity eventをjournalへ追加する。"""
        ...

    async def get_by_id(self, activity_id: ActivityId) -> ActivityEventRecord | None:
        """Activity IDでeventを取得する。"""
        ...

    async def has_seen_provider_event(
        self,
        *,
        source: str,
        provider_event_id: str,
    ) -> bool:
        """Provider eventがbounded dedupe window内にあるか返す。"""
        ...


class InMemoryActivityJournal(ActivityJournal):
    """process内のbounded activity event journal。

    Provider-event deduplicationは同じbounded window内だけの保証であり、
    永続的なidempotency boundaryではない。
    """

    def __init__(self, max_events: int = 1024) -> None:
        """最大保持event数を指定してjournalを初期化する。"""
        if max_events < 1:
            _raise_invalid_max_events()
        self._max_events = max_events
        self._events_by_id: dict[ActivityId, ActivityEventRecord] = {}
        self._event_order: deque[ActivityId] = deque()
        self._provider_events: set[tuple[str, str]] = set()

    @override
    async def append(self, event: ActivityEventRecord) -> ActivityAppendResult:
        """重複していないeventをjournalへ追加する。

        Returns:
            append結果。重複provider eventはaccepted=False。
        """
        provider_key = self._provider_key(event)
        if provider_key is not None and provider_key in self._provider_events:
            return ActivityAppendResult(
                accepted=False,
                event=None,
                reason=ActivityAppendSkipReason.DUPLICATE_PROVIDER_EVENT,
            )

        self._events_by_id[event.activity_id] = event
        self._event_order.append(event.activity_id)
        if provider_key is not None:
            self._provider_events.add(provider_key)
        self._evict_overflow()
        return ActivityAppendResult(accepted=True, event=event)

    @override
    async def get_by_id(self, activity_id: ActivityId) -> ActivityEventRecord | None:
        """Activity IDでeventを取得する。

        Returns:
            window内のevent。evictedまたは未保存の場合はNone。
        """
        return self._events_by_id.get(activity_id)

    @override
    async def has_seen_provider_event(
        self,
        *,
        source: str,
        provider_event_id: str,
    ) -> bool:
        """Provider eventがbounded dedupe window内にあるか返す。

        Returns:
            window内で見たeventならTrue。
        """
        return (source, provider_event_id) in self._provider_events

    def _evict_overflow(self) -> None:
        while len(self._event_order) > self._max_events:
            oldest_id = self._event_order.popleft()
            oldest_event = self._events_by_id.pop(oldest_id, None)
            if oldest_event is None:
                continue
            provider_key = self._provider_key(oldest_event)
            if provider_key is not None:
                self._provider_events.discard(provider_key)

    @staticmethod
    def _provider_key(event: ActivityEventRecord) -> tuple[str, str] | None:
        if event.source is None or event.provider_event_id is None:
            return None
        return (event.source, event.provider_event_id)


def _raise_invalid_max_events() -> None:
    message = "max_events must be at least 1"
    raise ValueError(message)
