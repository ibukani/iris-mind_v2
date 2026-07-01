"""Scheduler strict safety integration tests。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time

import pytest

from iris.contracts.actions import PresentedOutput
from iris.contracts.availability import AvailabilitySnapshot, AvailabilityStatus
from iris.contracts.delivery import DeliveryTarget
from iris.contracts.observations import IdleTickObservation, ObservationContext, ObservationKind
from iris.core.ids import ExternalRef, ObservationId, SessionId
from iris.runtime.delivery.in_memory import InMemoryDeliveryOutbox
from iris.runtime.scheduler.models import ScheduledObservation
from iris.runtime.scheduler.runner import SchedulerRunner
from iris.runtime.service import ObservationEnvelope, RuntimeResponse
from iris.runtime.state.safety_audit import (
    InMemorySafetyAuditJournal,
    SafetyAuditRecord,
    SafetyAuditStage,
)
from iris.safety.delivery_gate import (
    BasicDeliverySafetyGate,
    QuietHoursPolicy,
    StrictDeliverySafetyGate,
)
from iris.safety.policy_engine import DeliverySource, SafetyRiskLevel

pytestmark = pytest.mark.anyio
_NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)


@dataclass
class _Runtime:
    output: PresentedOutput

    async def handle_observation(self, envelope: ObservationEnvelope) -> RuntimeResponse:
        return RuntimeResponse(output=self.output, correlation_id=envelope.correlation_id)


class _Scheduler:
    async def due_observations(self, now: datetime) -> tuple[ScheduledObservation, ...]:
        return (
            ScheduledObservation(
                observation=IdleTickObservation(
                    observation_id=ObservationId("obs-strict"),
                    session_id=SessionId("session-1"),
                    context=ObservationContext(),
                    occurred_at=now,
                    kind=ObservationKind.IDLE_TICK,
                    reason="test",
                    idle_seconds=1000.0,
                ),
                correlation_id=None,
                reason="test",
                target=DeliveryTarget(
                    provider="discord",
                    provider_subject=ExternalRef("user-1"),
                    provider_space_ref=None,
                    session_id=SessionId("session-1"),
                ),
            ),
        )

    async def mark_dispatched(
        self, observation_id: ObservationId, *, dispatched_at: datetime
    ) -> None:
        _ = observation_id, dispatched_at

    async def mark_failed(
        self, observation_id: ObservationId, *, failed_at: datetime, reason: str
    ) -> None:
        _ = observation_id, failed_at, reason


@dataclass(frozen=True)
class _AvailabilityProvider:
    snapshot: AvailabilitySnapshot

    async def availability_for_target(
        self,
        target: DeliveryTarget,
        *,
        now: datetime,
    ) -> AvailabilitySnapshot:
        _ = target, now
        return self.snapshot


async def test_idle_tick_sensitive_context_is_blocked_audited_and_not_enqueued() -> None:
    """IdleTick strict block は reason を保持し outbox enqueue しない。"""
    outbox = InMemoryDeliveryOutbox()
    audit = InMemorySafetyAuditJournal()
    runner = SchedulerRunner(
        scheduler=_Scheduler(),
        runtime_service=_Runtime(
            PresentedOutput(
                text="generated output",
                policy_constraint_names=("sensitive_safety_context",),
            )
        ),
        delivery_gate=StrictDeliverySafetyGate(),
        outbox=outbox,
        safety_audit_journal=audit,
    )
    result = await runner.run_once(_NOW)
    assert result.results[0].status == "blocked"
    assert result.results[0].reason == "proactive_sensitive_safety_context"
    assert audit.records()[0].reason == "proactive_sensitive_safety_context"
    assert (
        await outbox.lease_due(provider="discord", now=_NOW, max_items=10, lease_seconds=30) == ()
    )


async def test_output_safety_reason_is_retained_and_audited() -> None:
    """Output safety block reason は no-send result と audit に残る。"""
    audit = InMemorySafetyAuditJournal()
    runner = SchedulerRunner(
        scheduler=_Scheduler(),
        runtime_service=_Runtime(
            PresentedOutput(text=None, safety_block_reason="output contains a secret-like pattern")
        ),
        delivery_gate=StrictDeliverySafetyGate(),
        outbox=InMemoryDeliveryOutbox(),
        safety_audit_journal=audit,
    )
    result = await runner.run_once(_NOW)
    assert result.results[0].reason == "output contains a secret-like pattern"
    assert audit.records()[0].stage.value == "output"


async def test_recent_blocks_for_same_target_block_proactive_delivery() -> None:
    """同一targetの直近block反復はenqueue前にproactive deliveryをblockする。"""
    audit = InMemorySafetyAuditJournal()
    for index in range(2):
        await audit.append(
            SafetyAuditRecord(
                observation_id=ObservationId(f"previous-{index}"),
                occurred_at=_NOW,
                stage=SafetyAuditStage.DELIVERY,
                allowed=False,
                reason="quiet_hours",
                risk_level=SafetyRiskLevel.MEDIUM,
                source=DeliverySource.PROACTIVE_IDLE_TICK,
                target_key="discord:user-1:",
                policy="strict_delivery",
                policy_version="1",
            )
        )
    outbox = InMemoryDeliveryOutbox()
    runner = SchedulerRunner(
        scheduler=_Scheduler(),
        runtime_service=_Runtime(PresentedOutput(text="generated output")),
        delivery_gate=StrictDeliverySafetyGate(),
        outbox=outbox,
        safety_audit_journal=audit,
    )

    result = await runner.run_once(_NOW)

    assert result.results[0].status == "blocked"
    assert result.results[0].reason == "repeated_recent_blocks"
    assert (
        await outbox.lease_due(provider="discord", now=_NOW, max_items=10, lease_seconds=30) == ()
    )


async def test_scheduler_records_proactive_busy_as_strict_delivery() -> None:
    """Scheduler audit はproactive BUSYをstrict provenanceで記録する。"""
    audit = InMemorySafetyAuditJournal()
    availability = AvailabilitySnapshot(
        actor_id=None,
        status=AvailabilityStatus.BUSY,
        reason="busy",
        observed_at=_NOW,
        computed_at=_NOW,
    )
    runner = SchedulerRunner(
        scheduler=_Scheduler(),
        runtime_service=_Runtime(PresentedOutput(text="generated output")),
        delivery_gate=StrictDeliverySafetyGate(),
        outbox=InMemoryDeliveryOutbox(),
        availability_provider=_AvailabilityProvider(availability),
        safety_audit_journal=audit,
    )

    result = await runner.run_once(_NOW)

    assert result.results[0].reason == "availability_busy"
    record = audit.records()[0]
    assert record.policy == "strict_delivery"
    assert record.risk_level is SafetyRiskLevel.MEDIUM
    assert record.source is DeliverySource.PROACTIVE_IDLE_TICK
    assert record.target_key == "discord:user-1:"


async def test_scheduler_records_proactive_quiet_hours_as_strict_delivery() -> None:
    """Scheduler audit はproactive quiet-hoursをstrict provenanceで記録する。"""
    audit = InMemorySafetyAuditJournal()
    gate = StrictDeliverySafetyGate(
        basic=BasicDeliverySafetyGate(
            quiet_hours=QuietHoursPolicy(
                enabled=True,
                start=time(11),
                end=time(13),
                timezone="UTC",
            )
        )
    )
    runner = SchedulerRunner(
        scheduler=_Scheduler(),
        runtime_service=_Runtime(PresentedOutput(text="generated output")),
        delivery_gate=gate,
        outbox=InMemoryDeliveryOutbox(),
        safety_audit_journal=audit,
    )

    result = await runner.run_once(_NOW)

    assert result.results[0].reason == "quiet_hours"
    record = audit.records()[0]
    assert record.policy == "strict_delivery"
    assert record.risk_level is SafetyRiskLevel.MEDIUM
    assert record.source is DeliverySource.PROACTIVE_IDLE_TICK
    assert record.target_key == "discord:user-1:"
