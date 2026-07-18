"""Process-local project context source。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import TYPE_CHECKING, override

from iris.contracts.retrieval import ProjectContextQuery, ProjectContextRecord, ProjectContextStore
from iris.core.datetime_utils import now_utc

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


class InMemoryProjectContextStore(ProjectContextStore):
    """Space scope と明示的な record だけを扱う project context store。"""

    def __init__(self, *, now: Callable[[], datetime] | None = None) -> None:
        """空の store を作る。"""
        self._records: dict[str, ProjectContextRecord] = {}
        self._lock = RLock()
        self._now = now or now_utc

    def put(self, record: ProjectContextRecord) -> None:
        """Project context record を scope付きで登録する。"""
        with self._lock:
            self._records[record.context_id] = record

    @override
    def query(self, query: ProjectContextQuery) -> Sequence[ProjectContextRecord]:
        """認可 scope、期限、簡易 lexical relevance で bounded に返す。

        Returns:
            scope内の期限内 project context。
        """
        if query.limit <= 0 or query.space_id is None or not query.text.strip():
            return ()
        with self._lock:
            records = tuple(self._records.values())
        current = self._now()
        candidates = [
            record
            for record in records
            if record.space_id == query.space_id
            and (record.actor_id is None or record.actor_id == query.actor_id)
            and (record.account_id is None or record.account_id == query.account_id)
            and (record.expires_at is None or record.expires_at > current)
        ]
        scored_values: list[tuple[float, datetime | None, ProjectContextRecord]] = [
            (_text_overlap(query.text, record.text), record.created_at, record)
            for record in candidates
        ]
        scored = sorted(
            scored_values,
            key=_project_sort_key,
            reverse=True,
        )
        return tuple(record for score, _, record in scored if score > 0.0)[: query.limit]


def _text_overlap(query: str, text: str) -> float:
    query_tokens = frozenset(query.casefold().split())
    text_tokens = frozenset(text.casefold().split())
    if query_tokens and text_tokens:
        return len(query_tokens & text_tokens) / len(query_tokens)
    return 1.0 if query.casefold() in text.casefold() else 0.0


def _project_sort_key(
    value: tuple[float, datetime | None, ProjectContextRecord],
) -> tuple[float, datetime, str]:
    return (value[0], value[1] or _minimum_datetime(), str(value[2].context_id))


def _minimum_datetime() -> datetime:
    """型推論用の epoch 値を返す。

    Returns:
        UTC timezone付き最小日時。
    """
    return datetime.min.replace(tzinfo=timezone(timedelta(0)))
