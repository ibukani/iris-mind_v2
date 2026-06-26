"""SchedulerRunner delivery boundary tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from iris.contracts.actions import PresentedOutput, SendMessageAction
from iris.contracts.availability import AvailabilitySnapshot, AvailabilityStatus
from iris.contracts.delivery import DeliveryStatus, DeliveryTarget
from iris.contracts.observations import IdleTickObservation, ObservationContext, ObservationKind
from iris.core.ids import AccountId, ExternalRef, ObservationId, SessionId, SpaceId
from iris.runtime.delivery.in_memory import InMemoryDeliveryOutbox
from iris.runtime.scheduler.models import ScheduledObservation
from iris.runtime.scheduler.runner import SchedulerRunner
from iris.runtime.service import ObservationEnvelope, RuntimeResponse
from iris.safety.delivery_gate import BasicDeliverySafetyGate, DeliverySafetyDecision

if TYPE_CHECKING:
    from iris.contracts.delivery import DeliveryEnvelope
    from iris.runtime.scheduler.ports import DeliveryAvailabilityProvider
    from iris.safety.delivery_gate import DeliverySafetyGate


pytestmark = pytest.mark.anyio

_NOW = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)


async def test_no_send_output_is_not_enqueued() -> None:
    """No-send runtime output does not create delivery item."""
    runner, runtime, outbox = _runner(PresentedOutput(text=None))

    result = await runner.run_once(_NOW)

    assert runtime.calls == 1
    assert result.results[0].status == "no_send"
    assert await _leased(outbox) == ()


async def test_delivery_disabled_blocks_without_enqueue() -> None:
    """Disabled delivery blocks sendable output before enqueue."""
    runner, _runtime, outbox = _runner(
        PresentedOutput(text="hello"),
        delivery_enabled=False,
    )

    result = await runner.run_once(_NOW)

    assert result.results[0].status == "blocked"
    assert result.results[0].reason == "delivery_disabled"
    assert await _leased(outbox) == ()


async def test_missing_delivery_target_blocks_without_enqueue() -> None:
    """Missing target blocks sendable output before delivery safety check."""
    runner, _runtime, outbox = _runner(PresentedOutput(text="hello"), has_target=False)

    result = await runner.run_once(_NOW)

    assert result.results[0].status == "blocked"
    assert result.results[0].reason == "missing_delivery_target"
    assert await _leased(outbox) == ()


async def test_delivery_safety_gate_block_prevents_enqueue() -> None:
    """DeliverySafetyGate BLOCK prevents enqueue."""
    runner, _runtime, outbox = _runner(
        PresentedOutput(text="hello"),
        delivery_gate=_BlockingGate(),
    )

    result = await runner.run_once(_NOW)

    assert result.results[0].status == "blocked"
    assert result.results[0].reason == "blocked_for_test"
    assert await _leased(outbox) == ()


async def test_delivery_safety_gate_allow_enqueues_send_message_action() -> None:
    """DeliverySafetyGate ALLOW enqueues a pull-based SendMessageAction."""
    runner, _runtime, outbox = _runner(PresentedOutput(text="hello"))

    result = await runner.run_once(_NOW)
    leased = await _leased(outbox)

    assert result.results[0].status == "enqueued"
    assert len(leased) == 1
    assert isinstance(leased[0].action, SendMessageAction)
    assert leased[0].status is DeliveryStatus.LEASED


async def test_availability_snapshot_is_propagated_to_delivery_gate() -> None:
    """SchedulerRunner passes availability snapshot into DeliverySafetyGate."""
    availability = _availability_snapshot(AvailabilityStatus.AVAILABLE)
    gate = _RecordingGate()
    runner, _runtime, outbox = _runner(
        PresentedOutput(text="hello"),
        availability_provider=_AvailabilityProvider(availability),
        delivery_gate=gate,
    )

    await runner.run_once(_NOW)

    assert gate.availability == availability
    assert len(await _leased(outbox)) == 1


async def test_runtime_failure_marks_scheduled_observation_failed() -> None:
    """RuntimeError from runtime service triggers scheduler.mark_failed."""
    scheduler = _RecordingScheduler()
    outbox = InMemoryDeliveryOutbox()
    runner = SchedulerRunner(
        scheduler=scheduler,
        runtime_service=_FailingRuntimeService(),
        delivery_gate=BasicDeliverySafetyGate(),
        outbox=outbox,
        delivery_enabled=True,
    )

    result = await runner.run_once(_NOW)

    assert result.results[0].status == "failed"
    assert len(scheduler.failures) == 1
    assert scheduler.failures[0].observation_id == ObservationId("obs-1")
    assert not scheduler.dispatched
    assert await _leased(outbox) == ()


def _runner(
    output: PresentedOutput,
    *,
    has_target: bool = True,
    delivery_enabled: bool = True,
    delivery_gate: DeliverySafetyGate | None = None,
    availability_provider: DeliveryAvailabilityProvider | None = None,
) -> tuple[SchedulerRunner, _RuntimeService, InMemoryDeliveryOutbox]:
    runtime = _RuntimeService(output)
    outbox = InMemoryDeliveryOutbox()
    runner = SchedulerRunner(
        scheduler=_SingleScheduler(has_target=has_target),
        runtime_service=runtime,
        delivery_gate=delivery_gate or BasicDeliverySafetyGate(),
        outbox=outbox,
        availability_provider=availability_provider,
        delivery_enabled=delivery_enabled,
    )
    return runner, runtime, outbox


async def _leased(outbox: InMemoryDeliveryOutbox) -> tuple[DeliveryEnvelope, ...]:
    return await outbox.lease_due(
        provider="discord",
        now=_NOW,
        max_items=10,
        lease_seconds=30,
    )


@dataclass
class _RuntimeService:
    output: PresentedOutput
    calls: int = 0

    async def handle_observation(self, envelope: ObservationEnvelope) -> RuntimeResponse:
        self.calls += 1
        return RuntimeResponse(output=self.output, correlation_id=envelope.correlation_id)


@dataclass
class _FailingRuntimeService:
    """RuntimeError を投げる runtime service（failure 境界テスト用）。"""

    async def handle_observation(self, envelope: ObservationEnvelope) -> RuntimeResponse:
        _ = envelope
        msg = "runtime processing failed"
        raise RuntimeError(msg)


class _SingleScheduler:
    def __init__(self, *, has_target: bool) -> None:
        self._target = _delivery_target() if has_target else None

    async def due_observations(self, now: datetime) -> tuple[ScheduledObservation, ...]:
        _ = now
        return (
            ScheduledObservation(
                observation=_idle_tick(),
                correlation_id=None,
                reason="test",
                target=self._target,
            ),
        )

    async def mark_dispatched(
        self,
        observation_id: ObservationId,
        *,
        dispatched_at: datetime,
    ) -> None:
        _ = observation_id, dispatched_at

    async def mark_failed(
        self,
        observation_id: ObservationId,
        *,
        failed_at: datetime,
        reason: str,
    ) -> None:
        _ = observation_id, failed_at, reason


@dataclass
class _FailureRecord:
    """mark_failed 呼び出しの記録。"""

    observation_id: ObservationId
    failed_at: datetime
    reason: str


class _RecordingScheduler:
    """mark_failed 呼び出しを記録する scheduler テストダブル。"""

    def __init__(self, *, has_target: bool = True) -> None:
        self._target = _delivery_target() if has_target else None
        self.dispatched: list[ObservationId] = []
        self.failures: list[_FailureRecord] = []

    async def due_observations(self, now: datetime) -> tuple[ScheduledObservation, ...]:
        _ = now
        return (
            ScheduledObservation(
                observation=_idle_tick(),
                correlation_id=None,
                reason="test",
                target=self._target,
            ),
        )

    async def mark_dispatched(
        self,
        observation_id: ObservationId,
        *,
        dispatched_at: datetime,
    ) -> None:
        _ = dispatched_at
        self.dispatched.append(observation_id)

    async def mark_failed(
        self,
        observation_id: ObservationId,
        *,
        failed_at: datetime,
        reason: str,
    ) -> None:
        self.failures.append(_FailureRecord(observation_id, failed_at, reason))


class _BlockingGate:
    async def check(
        self,
        *,
        target: DeliveryTarget,
        output: PresentedOutput,
        availability: AvailabilitySnapshot | None,
        now: datetime,
    ) -> DeliverySafetyDecision:
        _ = target, output, availability, now
        return DeliverySafetyDecision(allowed=False, reason="blocked_for_test")


class _RecordingGate:
    def __init__(self) -> None:
        self.availability: AvailabilitySnapshot | None = None

    async def check(
        self,
        *,
        target: DeliveryTarget,
        output: PresentedOutput,
        availability: AvailabilitySnapshot | None,
        now: datetime,
    ) -> DeliverySafetyDecision:
        _ = target, output, now
        self.availability = availability
        return DeliverySafetyDecision(allowed=True, reason="allowed_for_test")


@dataclass
class _AvailabilityProvider:
    snapshot: AvailabilitySnapshot

    async def availability_for_target(
        self,
        target: DeliveryTarget,
        *,
        now: datetime,
    ) -> AvailabilitySnapshot | None:
        _ = target, now
        return self.snapshot


def _idle_tick() -> IdleTickObservation:
    return IdleTickObservation(
        observation_id=ObservationId("obs-1"),
        session_id=SessionId("session-1"),
        context=ObservationContext(),
        occurred_at=_NOW,
        kind=ObservationKind.IDLE_TICK,
        reason="test",
        idle_seconds=1.0,
    )


def _availability_snapshot(status: AvailabilityStatus) -> AvailabilitySnapshot:
    return AvailabilitySnapshot(
        actor_id=None,
        status=status,
        reason="test",
        observed_at=_NOW,
        computed_at=_NOW,
        confidence=1.0,
    )


def _delivery_target() -> DeliveryTarget:
    return DeliveryTarget(
        provider="discord",
        provider_subject=ExternalRef("user-1"),
        provider_space_ref=ExternalRef("space-ref"),
        session_id=SessionId("session-1"),
        actor_id=None,
        account_id=AccountId("account-1"),
        space_id=SpaceId("space-1"),
    )
