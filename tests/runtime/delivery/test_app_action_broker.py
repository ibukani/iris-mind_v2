"""RuntimeAppActionBroker tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.contracts.actions import ActionResult, ActionStatus
from iris.contracts.delivery import DeliveryReport, DeliveryStatus
from iris.core.ids import ExternalRef
from iris.runtime.delivery.broker import RuntimeAppActionBroker
from iris.runtime.delivery.in_memory import InMemoryDeliveryOutbox
from tests.runtime.delivery.test_in_memory_delivery_outbox import envelope

pytestmark = pytest.mark.anyio


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
