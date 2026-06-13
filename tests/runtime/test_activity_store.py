"""activity store tests。"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from iris.contracts.activity import ActivityKind, ActivityRecord
from iris.core.ids import ActivityId, ActorId, ObservationId, SpaceId
from iris.runtime.activity.store import InMemoryActivityStore

_OCCURRED_AT = datetime(2026, 6, 13, tzinfo=UTC)


@pytest.mark.anyio
async def test_activity_store_records_and_indexes_activity() -> None:
    """recordをID、actor、spaceから取得できることを確認する。"""
    store = InMemoryActivityStore()
    record = _record()

    await store.record_activity(record)

    assert await store.get_by_id(record.activity_id) == record
    assert await store.latest_for_actor(ActorId("actor-1")) == record
    assert await store.latest_for_space(SpaceId("space-1")) == record


@pytest.mark.anyio
async def test_activity_store_deduplicates_provider_event() -> None:
    """同じsource/provider event IDの再記録を無視することを確認する。"""
    store = InMemoryActivityStore()
    first = _record()
    duplicate = replace(
        first,
        activity_id=ActivityId("activity:obs-2"),
        observation_id=ObservationId("obs-2"),
        received_at=first.received_at + timedelta(seconds=1),
    )

    await store.record_activity(first)
    await store.record_activity(duplicate)

    assert await store.get_by_id(duplicate.activity_id) is None
    assert await store.latest_for_actor(ActorId("actor-1")) == first
    assert await store.has_seen_provider_event(
        source="internal",
        provider_event_id="event-1",
    )


@pytest.mark.anyio
async def test_activity_store_records_events_without_provider_event_id() -> None:
    """Provider event IDなしのrecordを通常保存することを確認する。"""
    store = InMemoryActivityStore()
    first = replace(_record(), provider_event_id=None)
    second = replace(
        first,
        activity_id=ActivityId("activity:obs-2"),
        observation_id=ObservationId("obs-2"),
    )

    await store.record_activity(first)
    await store.record_activity(second)

    assert await store.get_by_id(first.activity_id) == first
    assert await store.get_by_id(second.activity_id) == second


def _record() -> ActivityRecord:
    return ActivityRecord(
        activity_id=ActivityId("activity:obs-1"),
        observation_id=ObservationId("obs-1"),
        provider_event_id="event-1",
        provider_sequence=1,
        actor_id=ActorId("actor-1"),
        account_id=None,
        device_id=None,
        space_id=SpaceId("space-1"),
        source="internal",
        kind=ActivityKind.VOICE_JOINED,
        occurred_at=_OCCURRED_AT,
        received_at=_OCCURRED_AT + timedelta(seconds=1),
    )
