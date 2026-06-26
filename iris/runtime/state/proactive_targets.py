"""Proactive delivery target store."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Protocol, override

if TYPE_CHECKING:
    from datetime import datetime

    from iris.contracts.delivery import DeliveryRouteHint
    from iris.core.ids import AccountId, ActorId, SessionId, SpaceId


@dataclass(frozen=True)
class ProactiveTarget:
    """Scheduler が IdleTickObservation を作る候補 target。"""

    actor_id: ActorId | None
    account_id: AccountId | None
    space_id: SpaceId | None
    session_id: SessionId
    route: DeliveryRouteHint
    display_name: str | None
    last_observed_at: datetime
    last_proactive_attempt_at: datetime | None = None


class ProactiveTargetStore(Protocol):
    """Proactive target を保存・列挙する runtime port。"""

    async def upsert_target(self, target: ProactiveTarget) -> None:
        """Target を stable key で upsert する。"""
        ...

    async def list_targets(
        self,
        *,
        now: datetime,
    ) -> tuple[ProactiveTarget, ...]:
        """Scheduler に見せる target を安定順で返す。"""
        ...

    async def mark_proactive_attempt(
        self,
        target: ProactiveTarget,
        *,
        attempted_at: datetime,
    ) -> None:
        """Target の proactive 試行時刻を記録する。"""
        ...


class InMemoryProactiveTargetStore(ProactiveTargetStore):
    """Process-local proactive target store."""

    def __init__(self) -> None:
        """Create an empty target store."""
        self._targets: dict[tuple[str, str, str, str], ProactiveTarget] = {}

    @override
    async def upsert_target(self, target: ProactiveTarget) -> None:
        """Insert or update a target by stable provider/session key."""
        key = _target_key(target)
        existing = self._targets.get(key)
        if existing is None:
            self._targets[key] = target
            return
        self._targets[key] = replace(
            target,
            last_proactive_attempt_at=existing.last_proactive_attempt_at,
        )

    @override
    async def list_targets(
        self,
        *,
        now: datetime,
    ) -> tuple[ProactiveTarget, ...]:
        """Return all targets in deterministic order."""
        return tuple(sorted(self._targets.values(), key=_target_key))

    @override
    async def mark_proactive_attempt(
        self,
        target: ProactiveTarget,
        *,
        attempted_at: datetime,
    ) -> None:
        """Update one target's proactive attempt timestamp."""
        key = _target_key(target)
        if key in self._targets:
            self._targets[key] = replace(
                self._targets[key],
                last_proactive_attempt_at=attempted_at,
            )


def _target_key(target: ProactiveTarget) -> tuple[str, str, str, str]:
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
