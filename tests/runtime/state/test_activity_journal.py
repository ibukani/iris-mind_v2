"""activity journal tests。"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from iris.contracts.activity import ActivityEventRecord, ActivityKind
from iris.core.ids import ActivityId, ActorId, ObservationId, SpaceId
from iris.runtime.state.activity_journal import (
    ActivityAppendSkipReason,
    InMemoryActivityJournal,
)
from iris.runtime.state.activity_projection import InMemoryActivityProjectionStore

_OCCURRED_AT = datetime(2026, 6, 13, tzinfo=UTC)


@pytest.mark.anyio
async def test_activity_journal_appends_new_event() -> None:
    """新しいactivity eventをbounded journalへ保存する。"""
    journal = InMemoryActivityJournal()
    event = _event()

    result = await journal.append(event)

    assert result.accepted
    assert result.event == event
    assert await journal.get_by_id(event.activity_id) == event


@pytest.mark.anyio
async def test_activity_journal_rejects_duplicate_activity_id() -> None:
    """同じactivity_idの再投入はDUPLICATE_ACTIVITY_IDで拒否する。"""
    journal = InMemoryActivityJournal()
    event = _event()

    first = await journal.append(event)
    second = await journal.append(event)

    assert first.accepted
    assert not second.accepted
    assert second.event is None
    assert second.reason is ActivityAppendSkipReason.DUPLICATE_ACTIVITY_ID
    assert await journal.get_by_id(event.activity_id) == event


@pytest.mark.anyio
async def test_activity_journal_rejects_duplicate_provider_event() -> None:
    """同じsource/provider event IDの重複eventを受理しない。"""
    journal = InMemoryActivityJournal()
    first = _event()
    duplicate = replace(first, activity_id=ActivityId("activity:obs-2"))

    await journal.append(first)
    result = await journal.append(duplicate)

    assert not result.accepted
    assert result.event is None
    assert result.reason is ActivityAppendSkipReason.DUPLICATE_PROVIDER_EVENT
    assert await journal.get_by_id(duplicate.activity_id) is None


@pytest.mark.anyio
async def test_activity_projection_updates_only_after_accepted_event() -> None:
    """projectionはaccepted eventだけで更新される。"""
    journal = InMemoryActivityJournal()
    projections = InMemoryActivityProjectionStore()
    first = _event()
    duplicate = replace(
        first,
        activity_id=ActivityId("activity:obs-2"),
        observation_id=ObservationId("obs-2"),
        kind=ActivityKind.VOICE_LEFT,
    )

    first_result = await journal.append(first)
    if first_result.event is not None:
        await projections.update_latest(first_result.event)
    duplicate_result = await journal.append(duplicate)
    if duplicate_result.accepted and duplicate_result.event is not None:
        await projections.update_latest(duplicate_result.event)

    assert await projections.latest_for_actor(ActorId("actor-1")) == first
    assert await projections.latest_for_space(SpaceId("space-1")) == first


@pytest.mark.anyio
async def test_activity_journal_eviction_does_not_clear_projection() -> None:
    """Bounded journal eviction後もprojectionは独立して残る。"""
    journal = InMemoryActivityJournal(max_events=1)
    projections = InMemoryActivityProjectionStore()
    first = _event()
    second = _event(
        activity_id=ActivityId("activity:obs-2"),
        observation_id=ObservationId("obs-2"),
        provider_event_id="event-2",
        occurred_at=_OCCURRED_AT + timedelta(seconds=1),
    )

    first_result = await journal.append(first)
    if first_result.event is not None:
        await projections.update_latest(first_result.event)
    second_result = await journal.append(second)
    if second_result.event is not None:
        await projections.update_latest(second_result.event)

    assert await journal.get_by_id(first.activity_id) is None
    assert await journal.get_by_id(second.activity_id) == second
    assert (
        await journal.has_seen_provider_event(
            source="internal",
            provider_event_id="event-1",
        )
        is False
    )
    assert await projections.latest_for_actor(ActorId("actor-1")) == second


def _event(
    *,
    activity_id: ActivityId | None = None,
    observation_id: ObservationId | None = None,
    provider_event_id: str | None = "event-1",
    occurred_at: datetime = _OCCURRED_AT,
) -> ActivityEventRecord:
    return ActivityEventRecord(
        activity_id=activity_id or ActivityId("activity:obs-1"),
        observation_id=observation_id or ObservationId("obs-1"),
        provider_event_id=provider_event_id,
        provider_sequence=1,
        actor_id=ActorId("actor-1"),
        account_id=None,
        device_id=None,
        space_id=SpaceId("space-1"),
        source="internal",
        kind=ActivityKind.VOICE_JOINED,
        occurred_at=occurred_at,
        received_at=occurred_at + timedelta(seconds=1),
    )
