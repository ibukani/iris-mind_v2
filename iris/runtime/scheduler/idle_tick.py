"""IdleTickObservation scheduler source."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from iris.contracts.delivery import DeliveryTarget, SchedulerTarget
from iris.contracts.observations import IdleTickObservation, ObservationContext, ObservationKind
from iris.core.ids import CorrelationId, ObservationId
from iris.runtime.scheduler.models import ScheduledObservation
from iris.runtime.scheduler.ports import RuntimeScheduler
from iris.safety.policy_engine import DeliverySource

if TYPE_CHECKING:
    from datetime import datetime

    from iris.runtime.state.scheduler_targets import SchedulerTargetStore


@dataclass(frozen=True)
class IdleTickSchedulePolicy:
    """Idle tick source の発火 policy。"""

    idle_threshold_seconds: float = 600.0
    min_interval_per_target_seconds: float = 1800.0
    max_due_per_run: int = 10


_DEFAULT_IDLE_POLICY = IdleTickSchedulePolicy()


class IdleTickSource(RuntimeScheduler):
    """SchedulerTargetStore から IdleTickObservation を生成する scheduler。"""

    def __init__(
        self,
        target_store: SchedulerTargetStore,
        *,
        policy: IdleTickSchedulePolicy = _DEFAULT_IDLE_POLICY,
    ) -> None:
        """Create an idle tick source."""
        self._target_store = target_store
        self._policy = policy
        self._failed: dict[ObservationId, tuple[datetime, str]] = {}

    @override
    async def due_observations(
        self,
        now: datetime,
    ) -> tuple[ScheduledObservation, ...]:
        """Idle threshold を超えた target を due observation として返す。

        Returns:
            due した ScheduledObservation のタプル。
        """
        due: list[ScheduledObservation] = []
        targets = await self._target_store.list_targets(now=now)
        for target in targets:
            if len(due) >= self._policy.max_due_per_run:
                break
            if not self._is_due(target, now):
                continue
            due.append(self._scheduled_observation_for(target, now))
        return tuple(due)

    @override
    async def mark_dispatched(
        self,
        observation_id: ObservationId,
        *,
        dispatched_at: datetime,
    ) -> None:
        """Dispatch 時刻を target store に反映する。"""
        targets = await self._target_store.list_targets(now=dispatched_at)
        for target in targets:
            if _observation_id_for(target, dispatched_at) == observation_id:
                await self._target_store.mark_scheduler_attempt(
                    target,
                    attempted_at=dispatched_at,
                )
                return

    @override
    async def mark_failed(
        self,
        observation_id: ObservationId,
        *,
        failed_at: datetime,
        reason: str,
    ) -> None:
        """Failure を process-local に記録する。"""
        self._failed[observation_id] = (failed_at, reason)

    @staticmethod
    def _scheduled_observation_for(
        target: SchedulerTarget,
        now: datetime,
    ) -> ScheduledObservation:
        """Build a ScheduledObservation with IdleTickObservation for one target.

        Returns:
            IdleTickObservation と DeliveryTarget を持つ ScheduledObservation。
        """
        observation_id = _observation_id_for(target, now)
        context = ObservationContext(
            actor=None,
            account_id=target.account_id,
            space_id=target.space_id,
            source="runtime_scheduler",
        )
        idle_seconds = (now - target.last_observed_at).total_seconds()
        observation = IdleTickObservation(
            observation_id=observation_id,
            session_id=target.session_id,
            context=context,
            occurred_at=now,
            kind=ObservationKind.IDLE_TICK,
            reason="proactive_idle_tick",
            idle_seconds=idle_seconds,
        )
        return ScheduledObservation(
            observation=observation,
            correlation_id=CorrelationId(f"scheduler:{observation_id}"),
            reason="idle_threshold_exceeded",
            delivery_source=DeliverySource.PROACTIVE_IDLE_TICK,
            target=DeliveryTarget(
                provider=target.route.provider,
                provider_subject=target.route.provider_subject,
                provider_space_ref=target.route.provider_space_ref,
                session_id=target.session_id,
                actor_id=target.actor_id,
                account_id=target.account_id,
                space_id=target.space_id,
                surface=target.route.surface,
            ),
        )

    def _is_due(self, target: SchedulerTarget, now: datetime) -> bool:
        """Return whether one target is idle enough."""
        if (now - target.last_observed_at).total_seconds() < self._policy.idle_threshold_seconds:
            return False
        last_attempt = target.last_scheduler_attempt_at
        if last_attempt is None:
            return True
        elapsed = (now - last_attempt).total_seconds()
        return elapsed >= self._policy.min_interval_per_target_seconds


def _observation_id_for(target: SchedulerTarget, now: datetime) -> ObservationId:
    """Build deterministic observation id for one scheduler run timestamp.

    Returns:
        決定論的な ObservationId。
    """
    subject = str(target.route.provider_subject or "none")
    space = str(target.route.provider_space_ref or "none")
    parts = (
        "idle",
        target.route.provider,
        subject,
        space,
        str(target.session_id),
        now.isoformat(),
    )
    return ObservationId(":".join(parts))
