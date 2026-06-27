"""Scheduler target store tests."""

from __future__ import annotations

from datetime import UTC, datetime

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
    await store.upsert_target(_target("user-1"))
    await store.mark_scheduler_attempt(
        _target("user-1"),
        attempted_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    await store.upsert_target(_target("user-1"))
    targets = await store.list_targets(now=datetime(2026, 1, 3, tzinfo=UTC))
    assert len(targets) == 1
    assert targets[0].last_scheduler_attempt_at == datetime(2026, 1, 2, tzinfo=UTC)


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
