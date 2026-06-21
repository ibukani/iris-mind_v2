"""InMemoryDeliveryOutbox state machine tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from iris.contracts.actions import ActionResult, ActionStatus, NoAction, SendMessageAction
from iris.contracts.delivery import DeliveryEnvelope, DeliveryStatus, DeliveryTarget
from iris.core.ids import ActionId, CorrelationId, DeliveryId, ExternalRef, LeaseId, SessionId
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


def _failed_result(
    leased: DeliveryEnvelope,
    *,
    error_reason: str = "temporary",
    external_message_id: ExternalRef | None = None,
) -> ActionResult:
    """Build FAILED ActionResult for a leased envelope.

    Returns:
        FAILED ActionResult with leased action identity.
    """
    return ActionResult(
        action_id=leased.action.action_id,
        correlation_id=leased.action.correlation_id,
        status=ActionStatus.FAILED,
        delivered_at=None,
        external_message_id=external_message_id,
        error_reason=error_reason,
    )


def _success_result(
    leased: DeliveryEnvelope,
    *,
    action_id: ActionId | None = None,
    correlation_id: CorrelationId | None = None,
    external_message_id: ExternalRef | None = None,
) -> ActionResult:
    """Build SUCCEEDED ActionResult for a leased envelope.

    Returns:
        SUCCEEDED ActionResult with leased action identity.
    """
    return ActionResult(
        action_id=action_id or leased.action.action_id,
        correlation_id=correlation_id or leased.action.correlation_id,
        status=ActionStatus.SUCCEEDED,
        delivered_at=datetime(2026, 1, 1, tzinfo=UTC),
        external_message_id=external_message_id or ExternalRef("msg-1"),
        error_reason=None,
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


async def test_same_lease_same_status_different_external_message_id_conflicts() -> None:
    """Same lease/status with changed external message id conflicts."""
    outbox = InMemoryDeliveryOutbox()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope())
    leased = (await outbox.lease_due(provider="discord", now=now, max_items=1, lease_seconds=30))[0]

    await outbox.complete(
        delivery_id=leased.delivery_id,
        lease_id=leased.lease_id,
        result=_success_result(leased, external_message_id=ExternalRef("msg-1")),
        completed_at=now,
    )

    with pytest.raises(DeliveryOutboxError, match="delivery_report_conflict"):
        await outbox.complete(
            delivery_id=leased.delivery_id,
            lease_id=leased.lease_id,
            result=_success_result(leased, external_message_id=ExternalRef("msg-2")),
            completed_at=now,
        )


async def test_same_lease_same_status_different_action_id_conflicts() -> None:
    """Same lease/status with changed action id conflicts."""
    outbox = InMemoryDeliveryOutbox()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope())
    leased = (await outbox.lease_due(provider="discord", now=now, max_items=1, lease_seconds=30))[0]

    await outbox.complete(
        delivery_id=leased.delivery_id,
        lease_id=leased.lease_id,
        result=_success_result(leased),
        completed_at=now,
    )

    with pytest.raises(DeliveryOutboxError, match="delivery_report_conflict"):
        await outbox.complete(
            delivery_id=leased.delivery_id,
            lease_id=leased.lease_id,
            result=_success_result(leased, action_id=ActionId("action-2")),
            completed_at=now,
        )


async def test_same_lease_same_status_different_correlation_id_conflicts() -> None:
    """Same lease/status with changed correlation id conflicts."""
    outbox = InMemoryDeliveryOutbox()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope())
    leased = (await outbox.lease_due(provider="discord", now=now, max_items=1, lease_seconds=30))[0]

    await outbox.complete(
        delivery_id=leased.delivery_id,
        lease_id=leased.lease_id,
        result=_success_result(leased),
        completed_at=now,
    )

    with pytest.raises(DeliveryOutboxError, match="delivery_report_conflict"):
        await outbox.complete(
            delivery_id=leased.delivery_id,
            lease_id=leased.lease_id,
            result=_success_result(leased, correlation_id=CorrelationId("corr-2")),
            completed_at=now,
        )


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
        result=_failed_result(leased, error_reason="temporary"),
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


async def test_lease_due_returns_only_leased_items() -> None:
    """lease_due never returns terminal or non-leased items."""
    outbox = InMemoryDeliveryOutbox()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope("delivery-1", idempotency_key="k1"))
    await outbox.enqueue(envelope("delivery-2", idempotency_key="k2"))
    blocked = await outbox.mark_blocked(
        delivery_id=DeliveryId("delivery-2"),
        reason="safety",
        blocked_at=now,
    )
    assert blocked.status is DeliveryStatus.BLOCKED
    leased = await outbox.lease_due(provider="discord", now=now, max_items=10, lease_seconds=30)
    assert len(leased) == 1
    assert all(item.status is DeliveryStatus.LEASED for item in leased)


async def test_expired_max_attempt_lease_becomes_permanent_and_is_not_returned() -> None:
    """Item past max attempts is FAILED_PERMANENT during lease and not returned."""
    outbox = InMemoryDeliveryOutbox()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope(max_attempts=1))
    first = await outbox.lease_due(provider="discord", now=now, max_items=1, lease_seconds=30)
    assert len(first) == 1
    released = await outbox.release(
        delivery_id=first[0].delivery_id,
        lease_id=first[0].lease_id,
        retry_after=now + timedelta(seconds=30),
        result=_failed_result(first[0], error_reason="temporary"),
        released_at=now,
    )
    assert released.status is DeliveryStatus.FAILED_PERMANENT
    after_expiry = await outbox.lease_due(
        provider="discord",
        now=now + timedelta(seconds=31),
        max_items=10,
        lease_seconds=30,
    )
    assert after_expiry == ()


async def test_repeated_failed_report_is_idempotent() -> None:
    """Repeated identical FAILED release is safe."""
    outbox = InMemoryDeliveryOutbox()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope(max_attempts=3))
    leased = (await outbox.lease_due(provider="discord", now=now, max_items=1, lease_seconds=30))[0]
    first = await outbox.release(
        delivery_id=leased.delivery_id,
        lease_id=leased.lease_id,
        retry_after=now + timedelta(seconds=30),
        result=_failed_result(leased, error_reason="timeout"),
        released_at=now,
    )
    assert first.status is DeliveryStatus.PENDING
    second_lease = (
        await outbox.lease_due(
            provider="discord",
            now=now + timedelta(seconds=31),
            max_items=1,
            lease_seconds=30,
        )
    )[0]
    second = await outbox.release(
        delivery_id=second_lease.delivery_id,
        lease_id=second_lease.lease_id,
        retry_after=now + timedelta(seconds=60),
        result=_failed_result(second_lease, error_reason="timeout"),
        released_at=now + timedelta(seconds=31),
    )
    assert second.status is DeliveryStatus.PENDING
    repeated = await outbox.release(
        delivery_id=second_lease.delivery_id,
        lease_id=second_lease.lease_id,
        retry_after=now + timedelta(seconds=60),
        result=_failed_result(second_lease, error_reason="timeout"),
        released_at=now + timedelta(seconds=31),
    )
    assert repeated.delivery_id == second.delivery_id


async def test_conflicting_report_after_recorded_report_raises() -> None:
    """Conflicting status after a recorded report raises DeliveryOutboxError."""
    outbox = InMemoryDeliveryOutbox()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope())
    leased = (await outbox.lease_due(provider="discord", now=now, max_items=1, lease_seconds=30))[0]
    success_result = ActionResult(
        action_id=leased.action.action_id,
        correlation_id=leased.action.correlation_id,
        status=ActionStatus.SUCCEEDED,
        delivered_at=now,
        external_message_id=ExternalRef("msg-1"),
        error_reason=None,
    )
    await outbox.complete(
        delivery_id=leased.delivery_id,
        lease_id=leased.lease_id,
        result=success_result,
        completed_at=now,
    )
    conflicting_result = replace(success_result, status=ActionStatus.CANCELLED)
    with pytest.raises(DeliveryOutboxError, match="delivery_report_conflict"):
        await outbox.complete(
            delivery_id=leased.delivery_id,
            lease_id=leased.lease_id,
            result=conflicting_result,
            completed_at=now,
        )


async def test_conflicting_lease_id_raises() -> None:
    """Different lease_id after a recorded terminal report raises DeliveryOutboxError."""
    outbox = InMemoryDeliveryOutbox()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope())
    leased = (await outbox.lease_due(provider="discord", now=now, max_items=1, lease_seconds=30))[0]
    success_result = ActionResult(
        action_id=leased.action.action_id,
        correlation_id=leased.action.correlation_id,
        status=ActionStatus.SUCCEEDED,
        delivered_at=now,
        external_message_id=ExternalRef("msg-1"),
        error_reason=None,
    )
    await outbox.complete(
        delivery_id=leased.delivery_id,
        lease_id=leased.lease_id,
        result=success_result,
        completed_at=now,
    )
    with pytest.raises(DeliveryOutboxError, match="delivery_already_terminal"):
        await outbox.complete(
            delivery_id=leased.delivery_id,
            lease_id=LeaseId("different-lease"),
            result=success_result,
            completed_at=now,
        )


async def test_delayed_duplicate_failed_report_after_re_lease_is_idempotent() -> None:
    """Delayed duplicate FAILED report for an old lease is safe after re-lease."""
    outbox = InMemoryDeliveryOutbox()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope(max_attempts=3))
    first_lease = (
        await outbox.lease_due(provider="discord", now=now, max_items=1, lease_seconds=30)
    )[0]
    first_release = await outbox.release(
        delivery_id=first_lease.delivery_id,
        lease_id=first_lease.lease_id,
        retry_after=now + timedelta(seconds=30),
        result=_failed_result(first_lease, error_reason="timeout"),
        released_at=now,
    )
    assert first_release.status is DeliveryStatus.PENDING
    second_lease = (
        await outbox.lease_due(
            provider="discord",
            now=now + timedelta(seconds=31),
            max_items=1,
            lease_seconds=30,
        )
    )[0]
    delayed_duplicate = await outbox.release(
        delivery_id=first_lease.delivery_id,
        lease_id=first_lease.lease_id,
        retry_after=now + timedelta(seconds=30),
        result=_failed_result(first_lease, error_reason="timeout"),
        released_at=now,
    )
    assert delayed_duplicate.delivery_id == first_release.delivery_id
    assert delayed_duplicate.status is DeliveryStatus.LEASED
    assert delayed_duplicate.lease_id == second_lease.lease_id
    assert delayed_duplicate.attempts == second_lease.attempts
    assert second_lease.lease_id != first_lease.lease_id
    assert (
        await outbox.lease_due(
            provider="discord",
            now=now + timedelta(seconds=31),
            max_items=1,
            lease_seconds=30,
        )
    ) == ()

    completed = await outbox.complete(
        delivery_id=second_lease.delivery_id,
        lease_id=second_lease.lease_id,
        result=_success_result(second_lease),
        completed_at=now + timedelta(seconds=31),
    )
    assert completed.status is DeliveryStatus.SUCCEEDED


async def test_stale_conflicting_report_after_re_lease_raises_conflict() -> None:
    """Same lease_id with different outcome after re-lease raises conflict."""
    outbox = InMemoryDeliveryOutbox()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope(max_attempts=3))
    first_lease = (
        await outbox.lease_due(provider="discord", now=now, max_items=1, lease_seconds=30)
    )[0]
    await outbox.release(
        delivery_id=first_lease.delivery_id,
        lease_id=first_lease.lease_id,
        retry_after=now + timedelta(seconds=30),
        result=_failed_result(first_lease, error_reason="timeout"),
        released_at=now,
    )
    await outbox.lease_due(
        provider="discord",
        now=now + timedelta(seconds=31),
        max_items=1,
        lease_seconds=30,
    )
    stale_success = ActionResult(
        action_id=first_lease.action.action_id,
        correlation_id=first_lease.action.correlation_id,
        status=ActionStatus.SUCCEEDED,
        delivered_at=now,
        external_message_id=ExternalRef("msg-1"),
        error_reason=None,
    )
    with pytest.raises(DeliveryOutboxError, match="delivery_report_conflict"):
        await outbox.complete(
            delivery_id=first_lease.delivery_id,
            lease_id=first_lease.lease_id,
            result=stale_success,
            completed_at=now,
        )


async def test_unknown_stale_report_after_re_lease_raises_lease_mismatch() -> None:
    """Report with unknown lease_id for a leased item raises lease_mismatch."""
    outbox = InMemoryDeliveryOutbox()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope(max_attempts=3))
    first_lease = (
        await outbox.lease_due(provider="discord", now=now, max_items=1, lease_seconds=30)
    )[0]
    await outbox.release(
        delivery_id=first_lease.delivery_id,
        lease_id=first_lease.lease_id,
        retry_after=now + timedelta(seconds=30),
        result=_failed_result(first_lease, error_reason="timeout"),
        released_at=now,
    )
    await outbox.lease_due(
        provider="discord",
        now=now + timedelta(seconds=31),
        max_items=1,
        lease_seconds=30,
    )
    with pytest.raises(DeliveryOutboxError, match="lease_mismatch"):
        await outbox.release(
            delivery_id=first_lease.delivery_id,
            lease_id=LeaseId("unknown-lease"),
            retry_after=now + timedelta(seconds=60),
            result=_failed_result(first_lease, error_reason="timeout"),
            released_at=now + timedelta(seconds=31),
        )
