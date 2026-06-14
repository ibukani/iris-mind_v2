"""SQLiteActivityJournalのテスト。"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from iris.contracts.activity import ActivityEventRecord, ActivityKind
from iris.core.ids import ActivityId, ActorId, ObservationId, SpaceId
from iris.runtime.activity.journal import ActivityAppendSkipReason
from iris.runtime.activity.sqlite_journal import SQLiteActivityJournal

if TYPE_CHECKING:
    from pathlib import Path


_OCCURRED_AT = datetime(2026, 6, 13, tzinfo=UTC)


def _build_event(
    *,
    activity_id: str = "activity:obs-1",
    provider_event_id: str = "event-1",
    occurred_at: datetime = _OCCURRED_AT,
) -> ActivityEventRecord:
    """Build a test ActivityEventRecord with overridable fields.

    Returns:
        ActivityEventRecord: 構築したテスト用event。
    """
    return ActivityEventRecord(
        activity_id=ActivityId(activity_id),
        observation_id=ObservationId("obs-1"),
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


@pytest.mark.anyio
async def test_sqlite_activity_journal_appends_and_reads_by_id(tmp_path: Path) -> None:
    """SQLiteActivityJournal stores and retrieves events by activity_id."""
    db_path = str(tmp_path / "activity_journal.db")
    event = _build_event()
    journal = SQLiteActivityJournal(db_path)

    result = await journal.append(event)

    assert result.accepted is True
    assert result.event == event
    assert result.reason is None
    assert await journal.get_by_id(event.activity_id) == event


@pytest.mark.anyio
async def test_sqlite_activity_journal_rejects_duplicate_provider_event(tmp_path: Path) -> None:
    """Duplicate source/provider_event_id is rejected with DUPLICATE_PROVIDER_EVENT."""
    db_path = str(tmp_path / "activity_journal.db")
    journal = SQLiteActivityJournal(db_path)
    event = _build_event()
    await journal.append(event)
    duplicate = replace(event, activity_id=ActivityId("activity:obs-2"))

    result = await journal.append(duplicate)

    assert result.accepted is False
    assert result.event is None
    assert result.reason is ActivityAppendSkipReason.DUPLICATE_PROVIDER_EVENT
    assert await journal.get_by_id(duplicate.activity_id) is None


@pytest.mark.anyio
async def test_sqlite_activity_journal_dedupe_survives_new_instance(tmp_path: Path) -> None:
    """Provider event dedupe survives a new SQLiteActivityJournal instance."""
    db_path = str(tmp_path / "activity_journal.db")
    event = _build_event()
    first = SQLiteActivityJournal(db_path)
    await first.append(event)
    duplicate = replace(event, activity_id=ActivityId("activity:obs-2"))
    reopened = SQLiteActivityJournal(db_path)

    result = await reopened.append(duplicate)

    assert result.accepted is False
    assert result.reason is ActivityAppendSkipReason.DUPLICATE_PROVIDER_EVENT
    assert await reopened.has_seen_provider_event(
        source=event.source or "internal",
        provider_event_id=event.provider_event_id or "event-1",
    )


@pytest.mark.anyio
async def test_sqlite_activity_journal_persists_across_reopen(tmp_path: Path) -> None:
    """Events are retrievable from a new SQLiteActivityJournal instance."""
    db_path = str(tmp_path / "activity_journal.db")
    event = _build_event()
    first = SQLiteActivityJournal(db_path)
    await first.append(event)
    reopened = SQLiteActivityJournal(db_path)

    assert await reopened.get_by_id(event.activity_id) == event


@pytest.mark.anyio
async def test_sqlite_activity_journal_does_not_depend_on_projection_store(tmp_path: Path) -> None:
    """SQLiteActivityJournal works independently of any projection store."""
    db_path = str(tmp_path / "activity_journal.db")
    event = _build_event()
    journal = SQLiteActivityJournal(db_path)

    result = await journal.append(event)

    assert result.accepted is True
    # Projection APIはjournal側に存在せず、書き込まれてもprojection更新は
    # 別経路(integrator)経由となる。
    assert not hasattr(journal, "update_latest")
    assert not hasattr(journal, "latest_for_actor")


@pytest.mark.anyio
async def test_sqlite_activity_journal_preserves_full_event_payload(tmp_path: Path) -> None:
    """Full event payload is stored and retrieved losslessly."""
    db_path = str(tmp_path / "activity_journal.db")
    journal = SQLiteActivityJournal(db_path)
    event = ActivityEventRecord(
        activity_id=ActivityId("activity:full"),
        observation_id=ObservationId("obs-full"),
        provider_event_id="provider-evt-99",
        provider_sequence=42,
        actor_id=ActorId("actor-full"),
        account_id=None,
        device_id=None,
        space_id=SpaceId("space-full"),
        source="discord",
        kind=ActivityKind.APP_OPENED,
        occurred_at=datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC),
        received_at=datetime(2026, 6, 13, 12, 0, 5, tzinfo=UTC),
        metadata={"channel": "general", "thread": "42"},
    )

    await journal.append(event)
    reopened = SQLiteActivityJournal(db_path)
    restored = await reopened.get_by_id(event.activity_id)

    assert restored is not None
    assert restored.activity_id == event.activity_id
    assert restored.provider_event_id == event.provider_event_id
    assert restored.provider_sequence == event.provider_sequence
    assert restored.actor_id == event.actor_id
    assert restored.space_id == event.space_id
    assert restored.source == event.source
    assert restored.kind == event.kind
    assert restored.occurred_at == event.occurred_at
    assert restored.received_at == event.received_at
    assert dict(restored.metadata) == {"channel": "general", "thread": "42"}


@pytest.mark.anyio
async def test_sqlite_activity_journal_has_seen_provider_event_returns_false_when_empty(
    tmp_path: Path,
) -> None:
    """Empty journal returns False for has_seen_provider_event."""
    db_path = str(tmp_path / "activity_journal.db")
    journal = SQLiteActivityJournal(db_path)

    result = await journal.has_seen_provider_event(
        source="internal",
        provider_event_id="never-seen",
    )

    assert result is False


@pytest.mark.anyio
async def test_sqlite_activity_journal_concurrent_instances_dedupe(tmp_path: Path) -> None:
    """Parallel SQLiteActivityJournal instances share persistent dedupe state."""
    db_path = str(tmp_path / "activity_journal.db")
    writer = SQLiteActivityJournal(db_path)
    event = _build_event()
    await writer.append(event)
    reader_a = SQLiteActivityJournal(db_path)
    reader_b = SQLiteActivityJournal(db_path)

    seen_a = await reader_a.has_seen_provider_event(
        source=event.source or "internal",
        provider_event_id=event.provider_event_id or "event-1",
    )
    seen_b = await reader_b.has_seen_provider_event(
        source=event.source or "internal",
        provider_event_id=event.provider_event_id or "event-1",
    )

    assert seen_a is True
    assert seen_b is True
