"""SQLiteDeliveryOutbox state machine parity tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from iris.contracts.actions import ActionResult, ActionStatus, NoAction, SendMessageAction
from iris.contracts.delivery import DeliveryEnvelope, DeliveryStatus, DeliveryTarget
from iris.core.ids import ActionId, CorrelationId, DeliveryId, ExternalRef, SessionId
from iris.runtime.delivery.outbox import DeliveryOutboxError
from iris.runtime.delivery.sqlite import SQLiteDeliveryOutbox

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.anyio


def _action(suffix: str = "1") -> SendMessageAction:
    return SendMessageAction(
        action_id=ActionId(f"action-{suffix}"),
        session_id=SessionId("session-1"),
        correlation_id=CorrelationId(f"corr-{suffix}"),
        text=f"hello {suffix}",
    )


def _envelope(suffix: str = "1", *, provider: str = "discord") -> DeliveryEnvelope:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return DeliveryEnvelope(
        delivery_id=DeliveryId(f"delivery-{suffix}"),
        action=_action(suffix),
        target=DeliveryTarget(
            provider=provider,
            provider_subject=ExternalRef("subject-1"),
            provider_space_ref=ExternalRef("space-1"),
            session_id=SessionId("session-1"),
        ),
        status=DeliveryStatus.PENDING,
        created_at=now,
        updated_at=now,
        not_before=None,
        attempts=0,
        max_attempts=3,
        idempotency_key=f"idem-{suffix}",
        lease_id=None,
        lease_expires_at=None,
        blocked_reason=None,
        last_error_reason=None,
    )


def _result(
    status: ActionStatus,
    *,
    suffix: str = "1",
    external_message_id: str | None = "external-1",
    error_reason: str | None = None,
) -> ActionResult:
    return ActionResult(
        action_id=ActionId(f"action-{suffix}"),
        correlation_id=CorrelationId(f"corr-{suffix}"),
        status=status,
        delivered_at=datetime(2026, 1, 1, 0, 0, 5, tzinfo=UTC),
        external_message_id=ExternalRef(external_message_id) if external_message_id else None,
        error_reason=error_reason,
    )


async def test_sqlite_enqueue_lease_and_reopen_persists_item(tmp_path: Path) -> None:
    """SQLite outbox persists pending items across store instances."""
    db_path = tmp_path / "state.sqlite3"
    outbox = SQLiteDeliveryOutbox(str(db_path))
    await outbox.enqueue(_envelope())

    reopened = SQLiteDeliveryOutbox(str(db_path))
    leased = await reopened.lease_due(
        provider="discord",
        now=datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
        max_items=10,
        lease_seconds=30.0,
    )

    assert len(leased) == 1
    assert leased[0].delivery_id == DeliveryId("delivery-1")
    assert leased[0].status is DeliveryStatus.LEASED


async def test_sqlite_enqueue_idempotent_by_idempotency_key(tmp_path: Path) -> None:
    """SQLite outbox returns the first envelope for repeated idempotency key."""
    outbox = SQLiteDeliveryOutbox(str(tmp_path / "state.sqlite3"))
    first = await outbox.enqueue(_envelope("1"))
    duplicate = replace(_envelope("2"), idempotency_key=first.idempotency_key)

    stored = await outbox.enqueue(duplicate)

    assert stored.delivery_id == first.delivery_id
    assert stored.action.action_id == first.action.action_id


async def test_sqlite_completed_report_is_idempotent_after_reopen(tmp_path: Path) -> None:
    """Report fingerprints persist so repeated ReportActionResult is idempotent."""
    db_path = tmp_path / "state.sqlite3"
    outbox = SQLiteDeliveryOutbox(str(db_path))
    await outbox.enqueue(_envelope())
    leased = (
        await outbox.lease_due(
            provider="discord",
            now=datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
            max_items=1,
            lease_seconds=30.0,
        )
    )[0]
    result = _result(ActionStatus.SUCCEEDED)
    completed = await outbox.complete(
        delivery_id=leased.delivery_id,
        lease_id=leased.lease_id,
        result=result,
        completed_at=datetime(2026, 1, 1, 0, 0, 2, tzinfo=UTC),
    )

    reopened = SQLiteDeliveryOutbox(str(db_path))
    repeated = await reopened.complete(
        delivery_id=leased.delivery_id,
        lease_id=leased.lease_id,
        result=result,
        completed_at=datetime(2026, 1, 1, 0, 0, 3, tzinfo=UTC),
    )

    assert completed.status is DeliveryStatus.SUCCEEDED
    assert repeated == completed


async def test_sqlite_same_lease_different_report_conflicts_after_reopen(
    tmp_path: Path,
) -> None:
    """SQLite report fingerprints reject conflicting repeated reports."""
    db_path = tmp_path / "state.sqlite3"
    outbox = SQLiteDeliveryOutbox(str(db_path))
    await outbox.enqueue(_envelope())
    leased = (
        await outbox.lease_due(
            provider="discord",
            now=datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
            max_items=1,
            lease_seconds=30.0,
        )
    )[0]
    await outbox.complete(
        delivery_id=leased.delivery_id,
        lease_id=leased.lease_id,
        result=_result(ActionStatus.SUCCEEDED, external_message_id="external-1"),
        completed_at=datetime(2026, 1, 1, 0, 0, 2, tzinfo=UTC),
    )

    reopened = SQLiteDeliveryOutbox(str(db_path))
    with pytest.raises(DeliveryOutboxError, match="delivery_report_conflict"):
        await reopened.complete(
            delivery_id=leased.delivery_id,
            lease_id=leased.lease_id,
            result=_result(ActionStatus.SUCCEEDED, external_message_id="external-2"),
            completed_at=datetime(2026, 1, 1, 0, 0, 3, tzinfo=UTC),
        )


async def test_sqlite_failed_release_retries_then_permanent(tmp_path: Path) -> None:
    """FAILED reports retry until max attempts, then become permanent."""
    outbox = SQLiteDeliveryOutbox(str(tmp_path / "state.sqlite3"))
    await outbox.enqueue(replace(_envelope(), max_attempts=2))
    first = (
        await outbox.lease_due(
            provider="discord",
            now=datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
            max_items=1,
            lease_seconds=1.0,
        )
    )[0]
    released = await outbox.release(
        delivery_id=first.delivery_id,
        lease_id=first.lease_id,
        retry_after=datetime(2026, 1, 1, 0, 0, 5, tzinfo=UTC),
        result=_result(ActionStatus.FAILED, external_message_id=None, error_reason="timeout"),
        released_at=datetime(2026, 1, 1, 0, 0, 2, tzinfo=UTC),
    )
    second = (
        await outbox.lease_due(
            provider="discord",
            now=datetime(2026, 1, 1, 0, 0, 6, tzinfo=UTC),
            max_items=1,
            lease_seconds=1.0,
        )
    )[0]
    permanent = await outbox.release(
        delivery_id=second.delivery_id,
        lease_id=second.lease_id,
        retry_after=datetime(2026, 1, 1, 0, 0, 8, tzinfo=UTC),
        result=_result(ActionStatus.FAILED, external_message_id=None, error_reason="timeout"),
        released_at=datetime(2026, 1, 1, 0, 0, 7, tzinfo=UTC),
    )

    assert released.status is DeliveryStatus.PENDING
    assert released.not_before == datetime(2026, 1, 1, 0, 0, 5, tzinfo=UTC)
    assert permanent.status is DeliveryStatus.FAILED_PERMANENT


async def test_sqlite_depth_limit_and_no_action_match_contract(tmp_path: Path) -> None:
    """SQLite outbox enforces active depth and rejects NoAction."""
    outbox = SQLiteDeliveryOutbox(str(tmp_path / "state.sqlite3"), max_depth_per_provider=1)
    await outbox.enqueue(_envelope("1"))

    with pytest.raises(DeliveryOutboxError, match="delivery_outbox_depth_exceeded"):
        await outbox.enqueue(_envelope("2"))

    no_action = replace(
        _envelope("3", provider="slack"),
        action=NoAction(
            action_id=ActionId("action-no"),
            session_id=SessionId("session-1"),
            correlation_id=CorrelationId("corr-no"),
            reason="silent",
        ),
    )
    with pytest.raises(DeliveryOutboxError, match="no_action_not_deliverable"):
        await outbox.enqueue(no_action)


async def test_sqlite_expired_max_attempt_lease_becomes_permanent(tmp_path: Path) -> None:
    """Expired leases at max attempts become permanent and are not returned."""
    outbox = SQLiteDeliveryOutbox(str(tmp_path / "state.sqlite3"))
    await outbox.enqueue(replace(_envelope(), max_attempts=1))
    first = await outbox.lease_due(
        provider="discord",
        now=datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
        max_items=1,
        lease_seconds=1.0,
    )

    second = await outbox.lease_due(
        provider="discord",
        now=datetime(2026, 1, 1, 0, 0, 3, tzinfo=UTC),
        max_items=1,
        lease_seconds=1.0,
    )
    stored = await outbox.get(first[0].delivery_id)

    assert second == ()
    assert stored.status is DeliveryStatus.FAILED_PERMANENT


async def test_sqlite_stale_failed_report_after_release_is_idempotent(
    tmp_path: Path,
) -> None:
    """A delayed duplicate FAILED report remains idempotent after re-lease."""
    outbox = SQLiteDeliveryOutbox(str(tmp_path / "state.sqlite3"))
    await outbox.enqueue(_envelope())
    first = (
        await outbox.lease_due(
            provider="discord",
            now=datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
            max_items=1,
            lease_seconds=1.0,
        )
    )[0]
    failed = _result(ActionStatus.FAILED, external_message_id=None, error_reason="timeout")
    released = await outbox.release(
        delivery_id=first.delivery_id,
        lease_id=first.lease_id,
        retry_after=datetime(2026, 1, 1, 0, 0, 2, tzinfo=UTC),
        result=failed,
        released_at=datetime(2026, 1, 1, 0, 0, 1, 500000, tzinfo=UTC),
    )
    await outbox.lease_due(
        provider="discord",
        now=datetime(2026, 1, 1, 0, 0, 3, tzinfo=UTC),
        max_items=1,
        lease_seconds=1.0,
    )

    duplicate = await outbox.release(
        delivery_id=first.delivery_id,
        lease_id=first.lease_id,
        retry_after=datetime(2026, 1, 1, 0, 0, 4, tzinfo=UTC),
        result=failed,
        released_at=datetime(2026, 1, 1, 0, 0, 3, 500000, tzinfo=UTC),
    )

    assert duplicate.status is DeliveryStatus.LEASED
    assert duplicate != released
