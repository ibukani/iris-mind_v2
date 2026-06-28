"""Scheduler target store runtime port."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, override

from iris.contracts.delivery import SchedulerTarget

if TYPE_CHECKING:
    from datetime import datetime


class SchedulerTargetStore(Protocol):
    """Scheduler target を保存・列挙する runtime port。"""

    async def upsert_target(self, target: SchedulerTarget) -> None:
        """Target を stable key で upsert する。"""
        ...

    async def list_targets(
        self,
        *,
        now: datetime,
    ) -> tuple[SchedulerTarget, ...]:
        """Scheduler に見せる target を安定順で返す。"""
        ...

    async def mark_scheduler_attempt(
        self,
        target: SchedulerTarget,
        *,
        attempted_at: datetime,
    ) -> None:
        """Target の scheduler 試行時刻を記録する。"""
        ...


class InMemorySchedulerTargetStore(SchedulerTargetStore):
    """Process-local scheduler target store."""

    def __init__(self) -> None:
        """Create an empty target store."""
        self._targets: dict[tuple[str, str, str, str], SchedulerTarget] = {}

    @override
    async def upsert_target(self, target: SchedulerTarget) -> None:
        """Insert or update a target by stable provider/session key."""
        key = _target_key(target)
        existing = self._targets.get(key)
        if existing is None:
            self._targets[key] = target
            return
        self._targets[key] = _with_scheduler_attempt(
            target, existing.last_scheduler_attempt_at
        )

    @override
    async def list_targets(
        self,
        *,
        now: datetime,
    ) -> tuple[SchedulerTarget, ...]:
        """Return non-stale targets in deterministic order."""
        active = (
            target
            for target in self._targets.values()
            if target.stale_after is None or target.stale_after > now
        )
        return tuple(sorted(active, key=_target_key))

    @override
    async def mark_scheduler_attempt(
        self,
        target: SchedulerTarget,
        *,
        attempted_at: datetime,
    ) -> None:
        """Update one target's scheduler attempt timestamp."""
        key = _target_key(target)
        if key in self._targets:
            self._targets[key] = _with_scheduler_attempt(self._targets[key], attempted_at)


def _target_key(target: SchedulerTarget) -> tuple[str, str, str, str]:
    """Return a deterministic sort/storage key for a target.

    Returns:
        Tuple of provider, subject, space ref, and session id strings.
    """
    return (
        target.route.provider,
        str(target.route.provider_subject or ""),
        str(target.route.provider_space_ref or ""),
        str(target.session_id),
    )


def _with_scheduler_attempt(
    target: SchedulerTarget,
    attempted_at: datetime | None,
) -> SchedulerTarget:
    """Scheduler attempt時刻を更新し、targetを再検証する。

    Returns:
        再構築したtarget。
    """
    return SchedulerTarget(
        actor_id=target.actor_id,
        account_id=target.account_id,
        space_id=target.space_id,
        session_id=target.session_id,
        route=target.route,
        display_name=target.display_name,
        last_observed_at=target.last_observed_at,
        last_scheduler_attempt_at=attempted_at,
        stale_after=target.stale_after,
    )
