"""InMemoryDeliveryOutbox state machine tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from iris.contracts.actions import ActionResult, ActionStatus, NoAction, SendMessageAction
from iris.contracts.delivery import DeliveryEnvelope, DeliveryStatus, DeliveryTarget
from iris.core.ids import ActionId, CorrelationId, DeliveryId, ExternalRef, SessionId
from iris.runtime.delivery.in_memory import DeliveryOutboxError, InMemoryDeliveryOutbox

pytestmark = pytest.mark.anyio


def _action(action_id: str = "action-1") -> SendMessageAction:
    return SendMessageAction(
        action_id=ActionId(action_id),
        session_id=SessionId("session-1"),
        correlation_id=CorrelationId("corr-1"),
        text="hello",
    )


def envelope(
    delivery_id: str = "delivery-1",
    *,
    provider: str = "discord",
    idempotency_key: str = "idem-1",
    max_attempts: int = 3,
) -> DeliveryEnvelope:
    """Build a PENDING DeliveryEnvelope for outbox tests.

    Returns:
        構成済みの DeliveryEnvelope。
    """
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return DeliveryEnvelope(
        delivery_id=DeliveryId(delivery_id),
        action=_action(),
        target=DeliveryTarget(
            provider=provider,
            provider_subject=ExternalRef("user-1"),
            provider_space_ref=None,
            session_id=SessionId("session-1"),
        ),
        status=DeliveryStatus.PENDING,
        created_at=now,
        updated_at=now,
        not_before=None,
        attempts=0,
        max_attempts=max_attempts,
        idempotency_key=idempotency_key,
    )


async def test_enqueue_then_lease_provider_scoped() -> None:
    """Enqueued pending item can be leased only for matching provider."""
    outbox = InMemoryDeliveryOutbox()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope())
    assert await outbox.lease_due(provider="slack", now=now, max_items=10, lease_seconds=30) == ()
    leased = await outbox.lease_due(provider="discord", now=now, max_items=10, lease_seconds=30)
    assert len(leased) == 1
    assert leased[0].status is DeliveryStatus.LEASED
    assert leased[0].attempts == 1
    assert leased[0].lease_id is not None


async def test_enqueue_idempotent_by_idempotency_key() -> None:
    """Repeated enqueue with same idempotency key returns original item."""
    outbox = InMemoryDeliveryOutbox()
    first = await outbox.enqueue(envelope("delivery-1", idempotency_key="same"))
    second = await outbox.enqueue(envelope("delivery-2", idempotency_key="same"))
    assert second.delivery_id == first.delivery_id


async def test_active_lease_not_returned_until_expired() -> None:
    """Active lease suppresses duplicate polling until expiry."""
    outbox = InMemoryDeliveryOutbox()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope())
    first = await outbox.lease_due(provider="discord", now=now, max_items=10, lease_seconds=30)
    assert len(first) == 1
    assert await outbox.lease_due(provider="discord", now=now, max_items=10, lease_seconds=30) == ()
    second = await outbox.lease_due(
        provider="discord",
        now=now + timedelta(seconds=31),
        max_items=10,
        lease_seconds=30,
    )
    assert len(second) == 1
    assert second[0].attempts == 2


async def test_success_completion_is_idempotent_and_not_polled_again() -> None:
    """Successful completion is terminal and repeated identical report is safe."""
    outbox = InMemoryDeliveryOutbox()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope())
    leased = (await outbox.lease_due(provider="discord", now=now, max_items=1, lease_seconds=30))[0]
    result = ActionResult(
        action_id=leased.action.action_id,
        correlation_id=leased.action.correlation_id,
        status=ActionStatus.SUCCEEDED,
        delivered_at=now,
        external_message_id=ExternalRef("msg-1"),
        error_reason=None,
    )
    completed = await outbox.complete(
        delivery_id=leased.delivery_id,
        lease_id=leased.lease_id,
        result=result,
        completed_at=now,
    )
    repeated = await outbox.complete(
        delivery_id=leased.delivery_id,
        lease_id=leased.lease_id,
        result=result,
        completed_at=now,
    )
    assert completed.status is DeliveryStatus.SUCCEEDED
    assert repeated.status is DeliveryStatus.SUCCEEDED
    assert await outbox.lease_due(provider="discord", now=now, max_items=10, lease_seconds=30) == ()


async def test_failed_item_can_retry_then_max_attempts_permanent() -> None:
    """Release retries until max attempts then becomes permanent."""
    outbox = InMemoryDeliveryOutbox()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope(max_attempts=1))
    leased = (await outbox.lease_due(provider="discord", now=now, max_items=1, lease_seconds=30))[0]
    released = await outbox.release(
        delivery_id=leased.delivery_id,
        lease_id=leased.lease_id,
        retry_after=now + timedelta(seconds=30),
        reason="temporary",
        released_at=now,
    )
    assert released.status is DeliveryStatus.FAILED_PERMANENT


async def test_blocked_item_is_terminal() -> None:
    """Blocked item is never leased."""
    outbox = InMemoryDeliveryOutbox()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    item = await outbox.enqueue(envelope())
    blocked = await outbox.mark_blocked(
        delivery_id=item.delivery_id,
        reason="safety",
        blocked_at=now,
    )
    assert blocked.status is DeliveryStatus.BLOCKED
    assert await outbox.lease_due(provider="discord", now=now, max_items=10, lease_seconds=30) == ()


async def test_no_action_is_not_accepted_for_delivery() -> None:
    """NoAction cannot be enqueued in DeliveryOutbox."""
    outbox = InMemoryDeliveryOutbox()
    no_action_envelope = replace(
        envelope(),
        action=NoAction(
            action_id=ActionId("action-no"),
            session_id=SessionId("session-1"),
            correlation_id=CorrelationId("corr-1"),
            reason="no send",
        ),
    )
    with pytest.raises(DeliveryOutboxError, match="no_action_not_deliverable"):
        await outbox.enqueue(no_action_envelope)
