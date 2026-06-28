"""SQLiteActivityJournalのテスト。"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import aiosqlite
import pytest

from iris.adapters.persistence.sqlite.stores.activity_journal import SQLiteActivityJournal
from iris.contracts.activity import ActivityEventRecord, ActivityKind
from iris.core.ids import ActivityId, ActorId, ObservationId, SpaceId
from iris.runtime.state.activity_journal import (
    ActivityAppendResult,
    ActivityAppendSkipReason,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
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


@pytest.fixture
async def journal(tmp_path: Path) -> AsyncGenerator[SQLiteActivityJournal]:
    """Fixture for SQLiteActivityJournal.

    Yields:
        The activity journal.
    """
    j = SQLiteActivityJournal(str(tmp_path / "activity_journal.db"))
    yield j
    await j.close()


@pytest.mark.anyio
async def test_sqlite_activity_journal_appends(journal: SQLiteActivityJournal) -> None:
    """SQLiteActivityJournal stores events."""
    event = _build_event()

    result = await journal.append(event)

    assert result.accepted is True
    assert result.event == event
    assert result.reason is None


@pytest.mark.anyio
async def test_sqlite_activity_journal_rejects_duplicate_provider_event(
    journal: SQLiteActivityJournal,
) -> None:
    """Duplicate source/provider_event_id is rejected with DUPLICATE_PROVIDER_EVENT."""
    event = _build_event()
    await journal.append(event)
    duplicate = replace(event, activity_id=ActivityId("activity:obs-2"))

    result = await journal.append(duplicate)

    assert result.accepted is False
    assert result.event is None
    assert result.reason is ActivityAppendSkipReason.DUPLICATE_PROVIDER_EVENT


@pytest.mark.anyio
async def test_sqlite_activity_journal_dedupe_survives_new_instance(tmp_path: Path) -> None:
    """Provider event dedupe survives a new SQLiteActivityJournal instance."""
    db_path = str(tmp_path / "activity_journal.db")
    event = _build_event()
    first = SQLiteActivityJournal(db_path)
    await first.append(event)
    await first.close()

    duplicate = replace(event, activity_id=ActivityId("activity:obs-2"))
    reopened = SQLiteActivityJournal(db_path)

    result = await reopened.append(duplicate)

    assert result.accepted is False
    assert result.reason is ActivityAppendSkipReason.DUPLICATE_PROVIDER_EVENT
    await reopened.close()


@pytest.mark.anyio
async def test_sqlite_activity_journal_does_not_depend_on_projection_store(
    journal: SQLiteActivityJournal,
) -> None:
    """SQLiteActivityJournal works independently of any projection store."""
    event = _build_event()

    result = await journal.append(event)

    assert result.accepted is True
    # Projection APIはjournal側に存在せず、書き込まれてもprojection更新は
    # 別経路(integrator)経由となる。
    assert not hasattr(journal, "update_latest")
    assert not hasattr(journal, "latest_for_actor")


@pytest.mark.anyio
async def test_sqlite_activity_journal_preserves_full_event_payload(
    journal: SQLiteActivityJournal,
) -> None:
    """Full event payload is stored and retrieved losslessly."""
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


@pytest.mark.anyio
async def test_sqlite_activity_journal_rejects_duplicate_activity_id(
    journal: SQLiteActivityJournal,
) -> None:
    """Reusing the same activity_id is rejected with DUPLICATE_ACTIVITY_ID."""
    event = _build_event()
    first = await journal.append(event)
    second = await journal.append(event)

    assert first.accepted is True
    assert second.accepted is False
    assert second.event is None
    assert second.reason is ActivityAppendSkipReason.DUPLICATE_ACTIVITY_ID


@pytest.mark.anyio
async def test_sqlite_activity_journal_activity_id_race_returns_activity_id(tmp_path: Path) -> None:
    """activity_id の PK 違反 IntegrityError は DUPLICATE_ACTIVITY_ID へ分類される。"""
    db_path = str(tmp_path / "activity_journal.db")
    journal = SQLiteActivityJournal(db_path)

    # Initialize DB schema first
    await journal.append(_build_event(activity_id="dummy", provider_event_id="dummy-event"))

    expected = _build_event()

    # 別 connection から同一 activity_id を直接挿入して PK 違反を誘発する。
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            """
            INSERT INTO activity_events (
                activity_id, source, provider_event_id, actor_id, space_id,
                activity_kind, occurred_at, received_at, payload_json
            ) VALUES (?, NULL, NULL, NULL, NULL, ?, ?, ?, ?)
            """,
            (
                str(expected.activity_id),
                expected.kind.value,
                expected.occurred_at.isoformat(),
                expected.received_at.isoformat(),
                "{}",
            ),
        )
        await conn.commit()

    result = await journal.append(expected)

    assert result.accepted is False
    assert result.event is None
    assert result.reason is ActivityAppendSkipReason.DUPLICATE_ACTIVITY_ID
    await journal.close()


@pytest.mark.anyio
async def test_sqlite_activity_journal_concurrent_append_dedupe(tmp_path: Path) -> None:
    """Concurrent append() calls for the same provider_event_id dedupe cleanly.

    IntegrityError を取りこぼさず、accepted=True は1件だけ、残りは
    DUPLICATE_PROVIDER_EVENT へ変換されることを検証する。
    """
    db_path = str(tmp_path / "activity_journal.db")
    base = _build_event()
    total = 20
    events = [replace(base, activity_id=ActivityId(f"activity:race-{i}")) for i in range(total)]

    # initialize schema first to avoid concurrent schema creation errors
    j = SQLiteActivityJournal(db_path)
    await j.append(_build_event(activity_id="dummy", provider_event_id="dummy"))
    await j.close()

    async def _attempt(e: ActivityEventRecord) -> ActivityAppendResult:
        # 各 append は独立したjournalインスタンスを用いて、共有DBに対する
        # 異なる connection 競合状態を再現する。
        journal = SQLiteActivityJournal(db_path)
        res = await journal.append(e)
        await journal.close()
        return res

    results = await asyncio.gather(*(_attempt(e) for e in events))

    accepted = [r for r in results if r.accepted]
    duplicates = [
        r for r in results if r.reason is ActivityAppendSkipReason.DUPLICATE_PROVIDER_EVENT
    ]
    assert len(accepted) == 1
    assert len(duplicates) == total - 1
