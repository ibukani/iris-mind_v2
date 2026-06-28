"""Scheduler target store tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from iris.contracts.delivery import DeliveryRouteHint, SchedulerTarget
from iris.core.ids import ExternalRef, SessionId
from iris.runtime.state.scheduler_targets import InMemorySchedulerTargetStore

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
            provider_space_ref=None,
        ),
        display_name=subject,
        last_observed_at=now,
    )


async def test_target_store_upserts_by_stable_key() -> None:
    """Upsert replaces existing target with same provider route and session."""
    store = InMemorySchedulerTargetStore()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = _target("user-1").model_copy(
        update={
            "last_observed_at": now,
            "stale_after": datetime(2026, 1, 1, 1, tzinfo=UTC),
        }
    )

    await store.upsert_target(t1)
    await store.mark_scheduler_attempt(
        t1,
        attempted_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    t2 = t1.model_copy(
        update={
            "last_observed_at": datetime(2026, 1, 2, 1, tzinfo=UTC),
            "stale_after": datetime(2026, 1, 2, 2, tzinfo=UTC),
        }
    )
    await store.upsert_target(t2)

    targets = await store.list_targets(now=datetime(2026, 1, 1, tzinfo=UTC))
    assert len(targets) == 1
    assert targets[0].last_scheduler_attempt_at == datetime(2026, 1, 2, tzinfo=UTC)
    assert targets[0].last_observed_at == t2.last_observed_at
    assert targets[0].stale_after == t2.stale_after


async def test_target_store_ordering_is_deterministic() -> None:
    """Targets are listed in stable provider route order."""
    store = InMemorySchedulerTargetStore()
    await store.upsert_target(_target("user-b"))
    await store.upsert_target(_target("user-a"))
    targets = await store.list_targets(now=datetime(2026, 1, 1, tzinfo=UTC))
    assert [target.route.provider_subject for target in targets] == [
        ExternalRef("user-a"),
        ExternalRef("user-b"),
    ]


async def test_target_store_filters_stale_targets() -> None:
    """InMemorySchedulerTargetStore filters out stale targets."""
    store = InMemorySchedulerTargetStore()
    now = datetime(2026, 1, 1, tzinfo=UTC)

    stale = _target("stale").model_copy(update={"stale_after": now - timedelta(seconds=1)})
    active = _target("active").model_copy(update={"stale_after": now + timedelta(seconds=1)})
    open_target = _target("open").model_copy(update={"stale_after": None})

    await store.upsert_target(stale)
    await store.upsert_target(active)
    await store.upsert_target(open_target)

    targets = await store.list_targets(now=now)
    assert len(targets) == 2
    assert {t.display_name for t in targets} == {"active", "open"}
