"""SQLite scheduler target store tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from iris.adapters.persistence.sqlite.stores.scheduler_targets import SQLiteSchedulerTargetStore
from iris.contracts.delivery import DeliveryRouteHint, SchedulerTarget
from iris.core.ids import ExternalRef, SessionId

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.anyio


def _target(subject: str, session: str = "session-1") -> SchedulerTarget:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return SchedulerTarget(
        actor_id=None,
        account_id=None,
        space_id=None,
        session_id=SessionId(session),
        route=DeliveryRouteHint(
            provider="discord",
            provider_subject=ExternalRef(subject),
            provider_space_ref=ExternalRef("space-1"),
            display_name=f"display-{subject}",
        ),
        display_name=f"name-{subject}",
        last_observed_at=now,
    )


async def test_sqlite_scheduler_target_upsert_preserves_attempt_after_reopen(
    tmp_path: Path,
) -> None:
    """SQLite target store keeps stable-key upsert and attempt timestamps durable."""
    db_path = tmp_path / "state.sqlite3"
    store = SQLiteSchedulerTargetStore(str(db_path))
    target = _target("subject-1")
    attempted_at = datetime(2026, 1, 1, 0, 10, tzinfo=UTC)
    await store.upsert_target(target)
    await store.mark_scheduler_attempt(target, attempted_at=attempted_at)

    reopened = SQLiteSchedulerTargetStore(str(db_path))
    await reopened.upsert_target(replace(target, display_name="new-name"))
    listed = await reopened.list_targets(now=datetime(2026, 1, 1, 0, 20, tzinfo=UTC))

    assert len(listed) == 1
    assert listed[0].display_name == "new-name"
    assert listed[0].last_scheduler_attempt_at == attempted_at

    await store.close()
    await reopened.close()


async def test_sqlite_scheduler_target_stale_after_persists_after_reopen(
    tmp_path: Path,
) -> None:
    """SQLite target store persists stale_after after reopen."""
    db_path = tmp_path / "state.sqlite3"
    store = SQLiteSchedulerTargetStore(str(db_path))
    target = replace(_target("subject-1"), stale_after=datetime(2026, 1, 2, tzinfo=UTC))
    await store.upsert_target(target)

    reopened = SQLiteSchedulerTargetStore(str(db_path))
    listed = await reopened.list_targets(now=datetime(2026, 1, 1, 0, 20, tzinfo=UTC))

    assert len(listed) == 1
    assert listed[0].stale_after == target.stale_after

    await store.close()
    await reopened.close()


async def test_sqlite_scheduler_target_ordering_is_deterministic(tmp_path: Path) -> None:
    """SQLite target store orders targets by stable storage key."""
    store = SQLiteSchedulerTargetStore(str(tmp_path / "state.sqlite3"))
    await store.upsert_target(_target("subject-b", "session-2"))
    await store.upsert_target(_target("subject-a", "session-1"))

    listed = await store.list_targets(now=datetime(2026, 1, 1, tzinfo=UTC))

    assert [target.route.provider_subject for target in listed] == [
        ExternalRef("subject-a"),
        ExternalRef("subject-b"),
    ]

    await store.close()


async def test_sqlite_scheduler_target_stale_after_filters_old_routes(
    tmp_path: Path,
) -> None:
    """SQLite target store filters routes whose stale_after is not in the future."""
    store = SQLiteSchedulerTargetStore(str(tmp_path / "state.sqlite3"))
    now = datetime(2026, 1, 1, 0, 10, tzinfo=UTC)
    await store.upsert_target(replace(_target("stale"), stale_after=now - timedelta(seconds=1)))
    await store.upsert_target(replace(_target("active"), stale_after=now + timedelta(seconds=1)))
    await store.upsert_target(_target("open"))

    listed = await store.list_targets(now=now)

    assert [target.route.provider_subject for target in listed] == [
        ExternalRef("active"),
        ExternalRef("open"),
    ]

    await store.close()
