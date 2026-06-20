"""Process-local DeliveryOutbox implementation."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import override

from iris.contracts.actions import ActionResult, ActionStatus, NoAction
from iris.contracts.delivery import (
    TERMINAL_DELIVERY_STATUSES,
    DeliveryEnvelope,
    DeliveryStatus,
)
from iris.core.ids import DeliveryId, LeaseId
from iris.runtime.delivery.outbox import DeliveryOutbox


class DeliveryOutboxError(RuntimeError):
    """Delivery outbox state transition failed."""


class InMemoryDeliveryOutbox(DeliveryOutbox):
    """Deterministic in-memory outbox for tests and local runtime."""

    def __init__(self) -> None:
        """Create an empty process-local outbox."""
        self._items: dict[DeliveryId, DeliveryEnvelope] = {}
        self._idempotency_index: dict[str, DeliveryId] = {}
        self._report_index: dict[DeliveryId, _ReportFingerprint] = {}
        self._lease_counter = 0

    @override
    async def enqueue(self, envelope: DeliveryEnvelope) -> DeliveryEnvelope:
        """Store a pending delivery item idempotently by idempotency key.

        Returns:
            The stored envelope, or the existing envelope for a repeated key.

        Raises:
            DeliveryOutboxError: If the action is NoAction or the key is empty.
        """
        if isinstance(envelope.action, NoAction):
            msg = "no_action_not_deliverable"
            raise DeliveryOutboxError(msg)
        if not envelope.idempotency_key:
            msg = "idempotency_key_required"
            raise DeliveryOutboxError(msg)
        existing_id = self._idempotency_index.get(envelope.idempotency_key)
        if existing_id is not None:
            return self._items[existing_id]
        self._items[envelope.delivery_id] = envelope
        self._idempotency_index[envelope.idempotency_key] = envelope.delivery_id
        return envelope

    @override
    async def lease_due(
        self,
        *,
        provider: str,
        now: datetime,
        max_items: int,
        lease_seconds: float,
    ) -> tuple[DeliveryEnvelope, ...]:
        """Lease due items for a provider, skipping active leases.

        Returns:
            Leased envelopes in deterministic created-at order.
            Items that reach FAILED_PERMANENT during leasing are stored
            but not returned to the caller.
        """
        due: list[DeliveryEnvelope] = []
        for item in sorted(self._items.values(), key=_envelope_sort_key):
            if len(due) >= max_items:
                break
            if item.target.provider != provider or not _is_due(item, now):
                continue
            leased = self._lease_item(item, now=now, lease_seconds=lease_seconds)
            self._items[leased.delivery_id] = leased
            if leased.status is DeliveryStatus.LEASED:
                due.append(leased)
        return tuple(due)

    @override
    async def complete(
        self,
        *,
        delivery_id: DeliveryId,
        lease_id: LeaseId | None,
        result: ActionResult,
        completed_at: datetime,
    ) -> DeliveryEnvelope:
        """Complete a leased item with idempotent repeated reporting.

        Returns:
            The completed envelope, or the existing one for a repeated report.

        Raises:
            DeliveryOutboxError: If the report conflicts, the item is already
                terminal without a recorded report, or the lease mismatches.
        """
        item = self._get(delivery_id)
        current = _complete_fingerprint(delivery_id, lease_id, result)
        previous = self._report_index.get(delivery_id)
        if previous is not None:
            if previous == current:
                return item
            msg = "delivery_report_conflict"
            raise DeliveryOutboxError(msg)
        if item.status in TERMINAL_DELIVERY_STATUSES:
            msg = "delivery_already_terminal"
            raise DeliveryOutboxError(msg)
        _require_matching_lease(item, lease_id)
        status = _delivery_status_from_action_status(result.status)
        completed = replace(
            item,
            status=status,
            updated_at=completed_at,
            lease_id=None,
            lease_expires_at=None,
            last_error_reason=result.error_reason,
        )
        self._items[delivery_id] = completed
        self._report_index[delivery_id] = current
        return completed

    @override
    async def release(
        self,
        *,
        delivery_id: DeliveryId,
        lease_id: LeaseId | None,
        retry_after: datetime,
        reason: str,
        released_at: datetime,
    ) -> DeliveryEnvelope:
        """Release a leased item for retry, or make it permanent after max attempts.

        Returns:
            The released envelope set to PENDING, or FAILED_PERMANENT past max
            attempts. A repeated identical failed report returns the existing
            item idempotently.

        Raises:
            DeliveryOutboxError: If the report conflicts, the item is already
                terminal without a recorded report, or the lease mismatches.
        """
        item = self._get(delivery_id)
        current = _release_fingerprint(delivery_id, lease_id, reason)
        previous = self._report_index.get(delivery_id)
        if previous is not None:
            if previous == current:
                return item
            msg = "delivery_report_conflict"
            raise DeliveryOutboxError(msg)
        if item.status in TERMINAL_DELIVERY_STATUSES:
            msg = "delivery_already_terminal"
            raise DeliveryOutboxError(msg)
        _require_matching_lease(item, lease_id)
        status = (
            DeliveryStatus.FAILED_PERMANENT
            if item.attempts >= item.max_attempts
            else DeliveryStatus.PENDING
        )
        released = replace(
            item,
            status=status,
            updated_at=released_at,
            not_before=retry_after if status is DeliveryStatus.PENDING else item.not_before,
            lease_id=None,
            lease_expires_at=None,
            last_error_reason=reason,
        )
        self._items[delivery_id] = released
        self._report_index[delivery_id] = current
        return released

    @override
    async def mark_blocked(
        self,
        *,
        delivery_id: DeliveryId,
        reason: str,
        blocked_at: datetime,
    ) -> DeliveryEnvelope:
        """Mark an item blocked as a terminal state.

        Returns:
            The blocked envelope, or the existing terminal envelope.
        """
        item = self._get(delivery_id)
        if item.status in TERMINAL_DELIVERY_STATUSES:
            return item
        blocked = replace(
            item,
            status=DeliveryStatus.BLOCKED,
            updated_at=blocked_at,
            lease_id=None,
            lease_expires_at=None,
            blocked_reason=reason,
        )
        self._items[delivery_id] = blocked
        return blocked

    def _lease_item(
        self,
        item: DeliveryEnvelope,
        *,
        now: datetime,
        lease_seconds: float,
    ) -> DeliveryEnvelope:
        """Return a leased copy of one due item.

        Returns:
            A LEASED copy, or a FAILED_PERMANENT copy when max attempts is exceeded.
        """
        self._report_index.pop(item.delivery_id, None)
        if item.attempts >= item.max_attempts:
            failed = replace(
                item,
                status=DeliveryStatus.FAILED_PERMANENT,
                updated_at=now,
                lease_id=None,
                lease_expires_at=None,
                last_error_reason="max_attempts_exceeded",
            )
            self._items[item.delivery_id] = failed
            return failed
        self._lease_counter += 1
        lease_id = LeaseId(f"lease-{self._lease_counter}")
        return replace(
            item,
            status=DeliveryStatus.LEASED,
            updated_at=now,
            attempts=item.attempts + 1,
            lease_id=lease_id,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
        )

    def _get(self, delivery_id: DeliveryId) -> DeliveryEnvelope:
        """Return item or raise a transition error.

        Returns:
            The stored envelope for the delivery id.

        Raises:
            DeliveryOutboxError: If the delivery id is unknown.
        """
        try:
            return self._items[delivery_id]
        except KeyError as exc:
            msg = "delivery_not_found"
            raise DeliveryOutboxError(msg) from exc


def _envelope_sort_key(item: DeliveryEnvelope) -> tuple[datetime, DeliveryId]:
    """Return a deterministic sort key for leasing.

    Returns:
        Tuple of created_at and delivery_id for stable ordering.
    """
    return (item.created_at, item.delivery_id)


type _ReportFingerprint = tuple[DeliveryId, LeaseId | None, str, str | None]


def _complete_fingerprint(
    delivery_id: DeliveryId,
    lease_id: LeaseId | None,
    result: ActionResult,
) -> _ReportFingerprint:
    """Build a report fingerprint for a complete() call.

    Returns:
        Tuple of delivery_id, lease_id, status value, and error reason.
    """
    return (delivery_id, lease_id, result.status.value, result.error_reason)


def _release_fingerprint(
    delivery_id: DeliveryId,
    lease_id: LeaseId | None,
    reason: str,
) -> _ReportFingerprint:
    """Build a report fingerprint for a release() call.

    Returns:
        Tuple of delivery_id, lease_id, failed status value, and reason.
    """
    return (delivery_id, lease_id, ActionStatus.FAILED.value, reason)


def _is_due(item: DeliveryEnvelope, now: datetime) -> bool:
    """Return True when an item can be leased now.

    Returns:
        True if the item is PENDING and due, or LEASED with an expired lease.
    """
    if item.status in TERMINAL_DELIVERY_STATUSES:
        return False
    if item.not_before is not None and item.not_before > now:
        return False
    if item.status is DeliveryStatus.PENDING:
        return True
    return (
        item.status is DeliveryStatus.LEASED
        and item.lease_expires_at is not None
        and item.lease_expires_at <= now
    )


def _require_matching_lease(item: DeliveryEnvelope, lease_id: LeaseId | None) -> None:
    """Validate leased completion/release ownership.

    Raises:
        DeliveryOutboxError: If the item is not leased or the lease id mismatches.
    """
    if item.status is not DeliveryStatus.LEASED:
        msg = "delivery_not_leased"
        raise DeliveryOutboxError(msg)
    if item.lease_id != lease_id:
        msg = "lease_mismatch"
        raise DeliveryOutboxError(msg)


def _delivery_status_from_action_status(status: ActionStatus) -> DeliveryStatus:
    """Map ActionResult status to terminal delivery status.

    Returns:
        The matching terminal DeliveryStatus.
    """
    if status is ActionStatus.SUCCEEDED:
        return DeliveryStatus.SUCCEEDED
    if status is ActionStatus.CANCELLED:
        return DeliveryStatus.CANCELLED
    if status is ActionStatus.BLOCKED:
        return DeliveryStatus.BLOCKED
    return DeliveryStatus.FAILED_PERMANENT
