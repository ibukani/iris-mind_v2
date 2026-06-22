"""RuntimeAppActionBroker tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from iris.adapters.app_gateway.ports import AppActionBrokerError
from iris.contracts.actions import ActionResult, ActionStatus
from iris.contracts.delivery import DeliveryEnvelope, DeliveryReport, DeliveryStatus
from iris.core.ids import ExternalRef
from iris.runtime.delivery.broker import RuntimeAppActionBroker
from iris.runtime.delivery.in_memory import InMemoryDeliveryOutbox
from tests.runtime.delivery.test_in_memory_delivery_outbox import envelope

pytestmark = pytest.mark.anyio


def _failed_report(
    leased: DeliveryEnvelope,
    *,
    now: datetime,
    error_reason: str = "network",
) -> DeliveryReport:
    """Build a FAILED DeliveryReport for a leased envelope.

    Returns:
        構成済みの DeliveryReport。
    """
    return DeliveryReport(
        delivery_id=leased.delivery_id,
        lease_id=leased.lease_id,
        result=ActionResult(
            action_id=leased.action.action_id,
            correlation_id=leased.action.correlation_id,
            status=ActionStatus.FAILED,
            delivered_at=None,
            external_message_id=None,
            error_reason=error_reason,
        ),
        reported_at=now,
    )


async def test_broker_polls_and_completes_success() -> None:
    """Broker leases actions and completes success reports."""
    outbox = InMemoryDeliveryOutbox()
    broker = RuntimeAppActionBroker(outbox=outbox)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope())
    leased = (await broker.poll_actions(provider="discord", now=now, max_items=1))[0]
    completed = await broker.report_action_result(
        DeliveryReport(
            delivery_id=leased.delivery_id,
            lease_id=leased.lease_id,
            result=ActionResult(
                action_id=leased.action.action_id,
                correlation_id=leased.action.correlation_id,
                status=ActionStatus.SUCCEEDED,
                delivered_at=now,
                external_message_id=ExternalRef("msg-1"),
                error_reason=None,
            ),
            reported_at=now,
        )
    )
    assert completed.status is DeliveryStatus.SUCCEEDED


async def test_broker_failure_releases_for_retry() -> None:
    """Broker releases failed reports for retry when attempts remain."""
    outbox = InMemoryDeliveryOutbox()
    broker = RuntimeAppActionBroker(outbox=outbox)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope(max_attempts=3))
    leased = (await broker.poll_actions(provider="discord", now=now, max_items=1))[0]
    released = await broker.report_action_result(
        DeliveryReport(
            delivery_id=leased.delivery_id,
            lease_id=leased.lease_id,
            result=ActionResult(
                action_id=leased.action.action_id,
                correlation_id=leased.action.correlation_id,
                status=ActionStatus.FAILED,
                delivered_at=None,
                external_message_id=None,
                error_reason="network",
            ),
            reported_at=now,
        )
    )
    assert released.status is DeliveryStatus.PENDING


async def test_failed_report_is_idempotent() -> None:
    """Repeated identical FAILED report is safe."""
    outbox = InMemoryDeliveryOutbox()
    broker = RuntimeAppActionBroker(outbox=outbox)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope(max_attempts=3))
    leased = (await broker.poll_actions(provider="discord", now=now, max_items=1))[0]
    report = _failed_report(leased, now=now)
    first = await broker.report_action_result(report)
    assert first.status is DeliveryStatus.PENDING
    second = await broker.report_action_result(report)
    assert second.delivery_id == first.delivery_id


async def test_repeated_failed_report_does_not_raise() -> None:
    """Repeated FAILED report after re-lease does not raise."""
    outbox = InMemoryDeliveryOutbox()
    broker = RuntimeAppActionBroker(outbox=outbox)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope(max_attempts=3))
    leased = (await broker.poll_actions(provider="discord", now=now, max_items=1))[0]
    await broker.report_action_result(_failed_report(leased, now=now))
    re_leased = (
        await broker.poll_actions(
            provider="discord",
            now=now + timedelta(seconds=31),
            max_items=1,
        )
    )[0]
    report2 = _failed_report(re_leased, now=now + timedelta(seconds=31))
    released = await broker.report_action_result(report2)
    assert released.status is DeliveryStatus.PENDING
    repeated = await broker.report_action_result(report2)
    assert repeated.delivery_id == released.delivery_id


async def test_cancelled_report_completes_terminal() -> None:
    """CANCELLED report becomes terminal DeliveryStatus.CANCELLED."""
    outbox = InMemoryDeliveryOutbox()
    broker = RuntimeAppActionBroker(outbox=outbox)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope())
    leased = (await broker.poll_actions(provider="discord", now=now, max_items=1))[0]
    cancelled = await broker.report_action_result(
        DeliveryReport(
            delivery_id=leased.delivery_id,
            lease_id=leased.lease_id,
            result=ActionResult(
                action_id=leased.action.action_id,
                correlation_id=leased.action.correlation_id,
                status=ActionStatus.CANCELLED,
                delivered_at=None,
                external_message_id=None,
                error_reason=None,
            ),
            reported_at=now,
        )
    )
    assert cancelled.status is DeliveryStatus.CANCELLED


async def test_blocked_report_completes_terminal() -> None:
    """BLOCKED report becomes terminal DeliveryStatus.BLOCKED."""
    outbox = InMemoryDeliveryOutbox()
    broker = RuntimeAppActionBroker(outbox=outbox)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope())
    leased = (await broker.poll_actions(provider="discord", now=now, max_items=1))[0]
    blocked = await broker.report_action_result(
        DeliveryReport(
            delivery_id=leased.delivery_id,
            lease_id=leased.lease_id,
            result=ActionResult(
                action_id=leased.action.action_id,
                correlation_id=leased.action.correlation_id,
                status=ActionStatus.BLOCKED,
                delivered_at=None,
                external_message_id=None,
                error_reason="policy",
            ),
            reported_at=now,
        )
    )
    assert blocked.status is DeliveryStatus.BLOCKED


async def test_conflicting_repeated_report_raises_clear_error() -> None:
    """Conflicting report after a recorded report raises AppActionBrokerError."""
    outbox = InMemoryDeliveryOutbox()
    broker = RuntimeAppActionBroker(outbox=outbox)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope())
    leased = (await broker.poll_actions(provider="discord", now=now, max_items=1))[0]
    success_report = DeliveryReport(
        delivery_id=leased.delivery_id,
        lease_id=leased.lease_id,
        result=ActionResult(
            action_id=leased.action.action_id,
            correlation_id=leased.action.correlation_id,
            status=ActionStatus.SUCCEEDED,
            delivered_at=now,
            external_message_id=ExternalRef("msg-1"),
            error_reason=None,
        ),
        reported_at=now,
    )
    await broker.report_action_result(success_report)
    conflicting_report = DeliveryReport(
        delivery_id=leased.delivery_id,
        lease_id=leased.lease_id,
        result=ActionResult(
            action_id=leased.action.action_id,
            correlation_id=leased.action.correlation_id,
            status=ActionStatus.CANCELLED,
            delivered_at=None,
            external_message_id=None,
            error_reason=None,
        ),
        reported_at=now,
    )
    with pytest.raises(AppActionBrokerError, match="delivery_report_conflict"):
        await broker.report_action_result(conflicting_report)


async def test_same_status_different_external_message_id_conflicts() -> None:
    """Broker preserves external message id in report conflict detection."""
    outbox = InMemoryDeliveryOutbox()
    broker = RuntimeAppActionBroker(outbox=outbox)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope())
    leased = (await broker.poll_actions(provider="discord", now=now, max_items=1))[0]

    await broker.report_action_result(
        DeliveryReport(
            delivery_id=leased.delivery_id,
            lease_id=leased.lease_id,
            result=ActionResult(
                action_id=leased.action.action_id,
                correlation_id=leased.action.correlation_id,
                status=ActionStatus.SUCCEEDED,
                delivered_at=now,
                external_message_id=ExternalRef("msg-1"),
                error_reason=None,
            ),
            reported_at=now,
        )
    )

    with pytest.raises(AppActionBrokerError, match="delivery_report_conflict"):
        await broker.report_action_result(
            DeliveryReport(
                delivery_id=leased.delivery_id,
                lease_id=leased.lease_id,
                result=ActionResult(
                    action_id=leased.action.action_id,
                    correlation_id=leased.action.correlation_id,
                    status=ActionStatus.SUCCEEDED,
                    delivered_at=now,
                    external_message_id=ExternalRef("msg-2"),
                    error_reason=None,
                ),
                reported_at=now,
            )
        )
