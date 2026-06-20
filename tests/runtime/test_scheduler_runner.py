"""SchedulerRunner tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from iris.contracts.actions import PresentedOutput, SendMessageAction
from iris.contracts.availability import AvailabilitySnapshot, AvailabilityStatus
from iris.contracts.delivery import DeliveryStatus
from iris.contracts.observations import IdleTickObservation, ObservationContext, ObservationKind
from iris.core.ids import ObservationId, SessionId
from iris.runtime.delivery.in_memory import InMemoryDeliveryOutbox
from iris.runtime.proactive.targets import InMemoryProactiveTargetStore
from iris.runtime.scheduler.idle_tick import IdleTickSource
from iris.runtime.scheduler.models import ScheduledObservation
from iris.runtime.scheduler.runner import SchedulerRunner
from iris.runtime.service import ObservationEnvelope, RuntimeResponse
from iris.safety.delivery_gate import BasicDeliverySafetyGate, DeliverySafetyDecision
from tests.runtime.scheduler.test_idle_tick_source import make_target

if TYPE_CHECKING:
    from iris.runtime.scheduler.ports import DeliveryAvailabilityProvider

pytestmark = pytest.mark.anyio


@dataclass
class _FakeRuntimeService:
    output: PresentedOutput
    calls: int = 0

    async def handle_observation(self, envelope: ObservationEnvelope) -> RuntimeResponse:
        """Record call and return configured output.

        Returns:
            設定済み output を持つ RuntimeResponse。
        """
        self.calls += 1
        return RuntimeResponse(output=self.output, correlation_id=envelope.correlation_id)


class _BlockingGate:
    async def check(self, **_kwargs: object) -> DeliverySafetyDecision:
        """Always block.

        Returns:
            常に blocked となる DeliverySafetyDecision。
        """
        return DeliverySafetyDecision(allowed=False, reason="blocked_for_test")


async def _runner(
    output: PresentedOutput,
    *,
    availability_provider: DeliveryAvailabilityProvider | None = None,
) -> tuple[SchedulerRunner, _FakeRuntimeService, InMemoryDeliveryOutbox]:
    """Build a SchedulerRunner wired to a fake runtime and in-memory outbox.

    Returns:
        (runner, fake_runtime, outbox) のタプル。
    """
    now = datetime(2026, 1, 1, tzinfo=UTC)
    store = InMemoryProactiveTargetStore()
    await store.upsert_target(make_target(observed_at=now - timedelta(seconds=1000)))
    scheduler = IdleTickSource(store)
    runtime = _FakeRuntimeService(output)
    outbox = InMemoryDeliveryOutbox()
    return (
        SchedulerRunner(
            scheduler=scheduler,
            runtime_service=runtime,
            delivery_gate=BasicDeliverySafetyGate(),
            outbox=outbox,
            availability_provider=availability_provider,
        ),
        runtime,
        outbox,
    )


async def test_due_idle_tick_goes_through_runtime_service_no_send_not_enqueued() -> None:
    """No-send output is dispatched but not enqueued."""
    runner, runtime, outbox = await _runner(PresentedOutput(text=None))
    result = await runner.run_once(datetime(2026, 1, 1, tzinfo=UTC))
    assert runtime.calls == 1
    assert result.results[0].status == "no_send"
    assert (
        await outbox.lease_due(
            provider="discord",
            now=datetime(2026, 1, 1, tzinfo=UTC),
            max_items=10,
            lease_seconds=30,
        )
        == ()
    )


async def test_sendable_output_becomes_send_message_action() -> None:
    """Sendable runtime output is enqueued as SendMessageAction."""
    runner, runtime, outbox = await _runner(PresentedOutput(text="hello"))
    result = await runner.run_once(datetime(2026, 1, 1, tzinfo=UTC))
    leased = await outbox.lease_due(
        provider="discord",
        now=datetime(2026, 1, 1, tzinfo=UTC),
        max_items=10,
        lease_seconds=30,
    )
    assert runtime.calls == 1
    assert result.results[0].status == "enqueued"
    assert isinstance(leased[0].action, SendMessageAction)
    assert leased[0].status is DeliveryStatus.LEASED
    assert leased[0].idempotency_key.startswith("proactive:")


async def test_blocked_delivery_gate_does_not_enqueue() -> None:
    """Blocked delivery safety decision does not enqueue."""
    runner, _runtime, outbox = await _runner(PresentedOutput(text="hello"))
    blocked = SchedulerRunner(
        scheduler=runner.scheduler,
        runtime_service=runner.runtime_service,
        delivery_gate=_BlockingGate(),
        outbox=outbox,
    )
    result = await blocked.run_once(datetime(2026, 1, 1, tzinfo=UTC))
    assert result.results[0].status == "blocked"
    assert (
        await outbox.lease_due(
            provider="discord",
            now=datetime(2026, 1, 1, tzinfo=UTC),
            max_items=10,
            lease_seconds=30,
        )
        == ()
    )


async def test_runtime_failure_marks_failed() -> None:
    """Runtime RuntimeError is marked failed."""

    class _FailingRuntime:
        async def handle_observation(self, envelope: ObservationEnvelope) -> RuntimeResponse:
            """Raise runtime failure.

            Args:
                envelope: 受信観測コンテナ。この実装では使用しない。

            Raises:
                RuntimeError: 常に送出する。
            """
            _ = envelope
            msg = "boom"
            raise RuntimeError(msg)

    observation = IdleTickObservation(
        observation_id=ObservationId("obs-1"),
        session_id=SessionId("session-1"),
        context=ObservationContext(),
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        kind=ObservationKind.IDLE_TICK,
        reason="test",
        idle_seconds=1.0,
    )
    scheduler = _SingleScheduler(observation)
    runner = SchedulerRunner(
        scheduler=scheduler,
        runtime_service=_FailingRuntime(),
        delivery_gate=BasicDeliverySafetyGate(),
        outbox=InMemoryDeliveryOutbox(),
    )
    result = await runner.run_once(datetime(2026, 1, 1, tzinfo=UTC))
    assert result.results[0].status == "failed"
    assert scheduler.failed == ObservationId("obs-1")


class _SingleScheduler:
    """RuntimeScheduler fake for failure path."""

    def __init__(self, observation: IdleTickObservation) -> None:
        self._observation = observation
        self.failed: ObservationId | None = None
        self.failed_at: datetime | None = None
        self.failed_reason: str | None = None

    async def due_observations(self, now: datetime) -> tuple[ScheduledObservation, ...]:
        """Return one scheduled observation.

        Args:
            now: 現在時刻。この実装では使用しない。

        Returns:
            単一の ScheduledObservation を持つタプル。
        """
        _ = now
        return (ScheduledObservation(self._observation, None, "test", None),)

    async def mark_dispatched(
        self,
        observation_id: ObservationId,
        *,
        dispatched_at: datetime,
    ) -> None:
        """No-op dispatch marker."""

    async def mark_failed(
        self,
        observation_id: ObservationId,
        *,
        failed_at: datetime,
        reason: str,
    ) -> None:
        """Record failure marker."""
        self.failed = observation_id
        self.failed_at = failed_at
        self.failed_reason = reason


@dataclass
class _FakeAvailabilityProvider:
    """DeliveryAvailabilityProvider fake for scheduler runner tests."""

    snapshot: AvailabilitySnapshot | None
    called_with_target: bool = False
    call_count: int = 0

    async def availability_for_target(
        self,
        target: object,
        *,
        now: datetime,
    ) -> AvailabilitySnapshot | None:
        """Record call and return configured snapshot.

        Args:
            target: 配信先。この実装では呼び出し記録のみに使用する。
            now: 現在時刻。この実装では使用しない。

        Returns:
            設定済みの AvailabilitySnapshot または None。
        """
        _ = now
        self.called_with_target = target is not None
        self.call_count += 1
        return self.snapshot


def _availability_snapshot(status: AvailabilityStatus) -> AvailabilitySnapshot:
    """Build an AvailabilitySnapshot with the given status.

    Returns:
        構成済みの AvailabilitySnapshot。
    """
    return AvailabilitySnapshot(
        actor_id=None,
        status=status,
        reason="test",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        computed_at=datetime(2026, 1, 1, tzinfo=UTC),
        confidence=1.0,
    )


async def test_busy_availability_blocks_enqueue() -> None:
    """BUSY availability blocks scheduler delivery enqueue."""
    provider = _FakeAvailabilityProvider(snapshot=_availability_snapshot(AvailabilityStatus.BUSY))
    runner, _runtime, outbox = await _runner(
        PresentedOutput(text="hello"),
        availability_provider=provider,
    )
    result = await runner.run_once(datetime(2026, 1, 1, tzinfo=UTC))
    assert result.results[0].status == "blocked"
    assert "availability_busy" in result.results[0].reason
    assert (
        await outbox.lease_due(
            provider="discord",
            now=datetime(2026, 1, 1, tzinfo=UTC),
            max_items=10,
            lease_seconds=30,
        )
        == ()
    )


async def test_unavailable_availability_blocks_enqueue() -> None:
    """UNAVAILABLE availability blocks scheduler delivery enqueue."""
    provider = _FakeAvailabilityProvider(
        snapshot=_availability_snapshot(AvailabilityStatus.UNAVAILABLE),
    )
    runner, _runtime, outbox = await _runner(
        PresentedOutput(text="hello"),
        availability_provider=provider,
    )
    result = await runner.run_once(datetime(2026, 1, 1, tzinfo=UTC))
    assert result.results[0].status == "blocked"
    assert "availability_unavailable" in result.results[0].reason
    assert (
        await outbox.lease_due(
            provider="discord",
            now=datetime(2026, 1, 1, tzinfo=UTC),
            max_items=10,
            lease_seconds=30,
        )
        == ()
    )


async def test_availability_provider_is_called_with_delivery_target() -> None:
    """Availability provider is called and allows sendable output."""
    provider = _FakeAvailabilityProvider(snapshot=None)
    runner, _runtime, outbox = await _runner(
        PresentedOutput(text="hello"),
        availability_provider=provider,
    )
    await runner.run_once(datetime(2026, 1, 1, tzinfo=UTC))
    assert provider.call_count == 1
    assert provider.called_with_target is True
    leased = await outbox.lease_due(
        provider="discord",
        now=datetime(2026, 1, 1, tzinfo=UTC),
        max_items=10,
        lease_seconds=30,
    )
    assert len(leased) == 1
