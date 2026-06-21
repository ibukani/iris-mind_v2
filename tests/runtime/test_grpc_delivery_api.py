"""Runtime gRPC delivery API tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.adapters.grpc.mappers import delivery_report_from_proto
from iris.contracts.actions import ActionResult, ActionStatus
from iris.contracts.delivery import DeliveryReport, DeliveryStatus
from iris.core.ids import ExternalRef
from iris.generated.iris.runtime.v1 import runtime_pb2
from iris.runtime.delivery.broker import RuntimeAppActionBroker
from iris.runtime.delivery.in_memory import DeliveryOutboxError, InMemoryDeliveryOutbox
from tests.runtime.delivery.test_in_memory_delivery_outbox import envelope

pytestmark = pytest.mark.anyio


async def test_poll_app_actions_leases_provider_scoped_actions() -> None:
    """Broker-backed API path leases only matching provider actions."""
    outbox = InMemoryDeliveryOutbox()
    broker = RuntimeAppActionBroker(outbox=outbox)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope(provider="discord"))
    await outbox.enqueue(envelope("delivery-2", provider="slack", idempotency_key="idem-2"))
    actions = await broker.poll_actions(provider="discord", now=now, max_items=10)
    assert len(actions) == 1
    assert actions[0].target.provider == "discord"


async def test_report_action_result_success_completes_delivery() -> None:
    """ReportActionResult success completes delivery."""
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


async def test_report_action_result_failure_releases_or_permanently_fails() -> None:
    """Failure reports release retryable item or permanent after max attempts."""
    outbox = InMemoryDeliveryOutbox()
    broker = RuntimeAppActionBroker(outbox=outbox)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope(max_attempts=1))
    leased = (await broker.poll_actions(provider="discord", now=now, max_items=1))[0]
    failed = await broker.report_action_result(
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
    assert failed.status is DeliveryStatus.FAILED_PERMANENT


def test_report_action_result_proto_mapping_is_idempotent_safe_contract() -> None:
    """Report DTO keeps delivery and lease identifiers for idempotent completion."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    report = delivery_report_from_proto(
        runtime_pb2.ReportActionResultRequest(
            delivery_id="delivery-1",
            lease_id="lease-1",
            action_id="action-1",
            correlation_id="corr-1",
            status="succeeded",
        ),
        now,
    )
    assert report.delivery_id == "delivery-1"
    assert report.lease_id == "lease-1"


async def test_report_action_result_failed_is_idempotent() -> None:
    """Repeated identical FAILED report is safe."""
    outbox = InMemoryDeliveryOutbox()
    broker = RuntimeAppActionBroker(outbox=outbox)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope(max_attempts=3))
    leased = (await broker.poll_actions(provider="discord", now=now, max_items=1))[0]
    report = DeliveryReport(
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
    first = await broker.report_action_result(report)
    second = await broker.report_action_result(report)
    assert second.delivery_id == first.delivery_id


async def test_report_action_result_cancelled_is_terminal() -> None:
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
    repeated = await broker.report_action_result(
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
    assert repeated.status is DeliveryStatus.CANCELLED


async def test_report_action_result_blocked_is_terminal() -> None:
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
    repeated = await broker.report_action_result(
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
    assert repeated.status is DeliveryStatus.BLOCKED


async def test_report_action_result_external_message_id_conflict_raises() -> None:
    """ReportActionResult conflicts when external message id changes."""
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

    with pytest.raises(DeliveryOutboxError, match="delivery_report_conflict"):
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
