"""IdleTickSource tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from iris.contracts.delivery import DeliveryRouteHint
from iris.contracts.observations import IdleTickObservation
from iris.core.ids import AccountId, ExternalRef, SessionId, SpaceId
from iris.runtime.scheduler.idle_tick import IdleTickSchedulePolicy, IdleTickSource
from iris.runtime.state.proactive_targets import InMemoryProactiveTargetStore, ProactiveTarget

pytestmark = pytest.mark.anyio


def make_target(
    subject: str = "user-1",
    *,
    observed_at: datetime,
    attempted_at: datetime | None = None,
) -> ProactiveTarget:
    """Build a deterministic ProactiveTarget for tests.

    Returns:
        構築された ProactiveTarget。
    """
    return ProactiveTarget(
        actor_id=None,
        account_id=AccountId("account-1"),
        space_id=SpaceId("space-1"),
        session_id=SessionId(f"session-{subject}"),
        route=DeliveryRouteHint(
            provider="discord",
            provider_subject=ExternalRef(subject),
            provider_space_ref=ExternalRef("space-ref"),
        ),
        display_name=subject,
        last_observed_at=observed_at,
        last_proactive_attempt_at=attempted_at,
    )


async def test_no_registered_targets_no_observations() -> None:
    """Empty target store produces no observations."""
    source = IdleTickSource(InMemoryProactiveTargetStore())
    assert await source.due_observations(datetime(2026, 1, 1, tzinfo=UTC)) == ()


async def test_idle_threshold_and_context_and_target() -> None:
    """Target over idle threshold emits IdleTickObservation with context and target."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    store = InMemoryProactiveTargetStore()
    await store.upsert_target(make_target(observed_at=now - timedelta(seconds=601)))
    source = IdleTickSource(store)
    due = await source.due_observations(now)
    assert len(due) == 1
    assert isinstance(due[0].observation, IdleTickObservation)
    assert due[0].observation.context.account_id == AccountId("account-1")
    assert due[0].observation.context.space_id == SpaceId("space-1")
    assert due[0].target is not None
    assert due[0].target.provider == "discord"


async def test_below_threshold_and_min_interval_suppress_ticks() -> None:
    """Recent activity or recent proactive attempt suppresses ticks."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    store = InMemoryProactiveTargetStore()
    await store.upsert_target(make_target("recent", observed_at=now - timedelta(seconds=10)))
    await store.upsert_target(
        make_target(
            "attempted",
            observed_at=now - timedelta(seconds=1000),
            attempted_at=now - timedelta(seconds=10),
        )
    )
    source = IdleTickSource(store)
    assert await source.due_observations(now) == ()


async def test_max_due_and_ordering_are_deterministic() -> None:
    """max_due_per_run truncates stable ordered targets."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    store = InMemoryProactiveTargetStore()
    base = make_target("b", observed_at=now - timedelta(seconds=1000))
    await store.upsert_target(base)
    await store.upsert_target(
        replace(base, route=replace(base.route, provider_subject=ExternalRef("a")))
    )
    source = IdleTickSource(store, policy=IdleTickSchedulePolicy(max_due_per_run=1))
    due = await source.due_observations(now)
    assert len(due) == 1
    assert due[0].target is not None
    assert due[0].target.provider_subject == ExternalRef("a")
