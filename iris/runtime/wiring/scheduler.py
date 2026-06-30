"""Scheduler runtime wiring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.runtime.scheduler.idle_tick import IdleTickSchedulePolicy, IdleTickSource
from iris.runtime.scheduler.runner import SchedulerRunner

if TYPE_CHECKING:
    from iris.runtime.config import IrisRuntimeConfig
    from iris.runtime.delivery.outbox import DeliveryOutbox
    from iris.runtime.scheduler.ports import DeliveryAvailabilityProvider
    from iris.runtime.service import IrisRuntimeService
    from iris.runtime.state.safety_audit import SafetyAuditJournal
    from iris.runtime.state.scheduler_targets import SchedulerTargetStore
    from iris.safety.delivery_gate import DeliverySafetyGate


def wire_runtime_scheduler(
    target_store: SchedulerTargetStore,
    config: IrisRuntimeConfig,
) -> IdleTickSource:
    """IdleTickObservation source を runtime config から組み立てる。

    Returns:
        構成済みの IdleTickSource。
    """
    return IdleTickSource(
        target_store,
        policy=IdleTickSchedulePolicy(
            idle_threshold_seconds=config.scheduler.idle_threshold_seconds,
            min_interval_per_target_seconds=config.scheduler.min_interval_per_target_seconds,
            max_due_per_run=config.scheduler.max_due_per_run,
        ),
    )


@dataclass(frozen=True)
class SchedulerSafetyDependencies:
    """Scheduler safety に必要な runtime ports。"""

    availability_provider: DeliveryAvailabilityProvider | None = None
    audit_journal: SafetyAuditJournal | None = None


def wire_scheduler_runner(
    *,
    runtime_service: IrisRuntimeService,
    scheduler: IdleTickSource,
    delivery_gate: DeliverySafetyGate,
    outbox: DeliveryOutbox,
    config: IrisRuntimeConfig,
    safety: SchedulerSafetyDependencies | None = None,
) -> SchedulerRunner:
    """SchedulerRunner を constructor injection で組み立てる。

    Returns:
        構成済みの SchedulerRunner。
    """
    safety_dependencies = safety or SchedulerSafetyDependencies()
    return SchedulerRunner(
        scheduler=scheduler,
        runtime_service=runtime_service,
        delivery_gate=delivery_gate,
        outbox=outbox,
        availability_provider=safety_dependencies.availability_provider,
        delivery_enabled=config.delivery.enabled,
        max_attempts=config.delivery.max_attempts,
        safety_audit_journal=safety_dependencies.audit_journal,
        recent_block_window_seconds=config.delivery.rate_limit_window_seconds,
    )
