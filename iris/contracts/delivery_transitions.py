"""DeliveryEnvelopeのbackend非依存状態遷移。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta
from typing import TYPE_CHECKING

from iris.contracts.actions import ActionResult, ActionStatus
from iris.contracts.delivery import (
    TERMINAL_DELIVERY_STATUSES,
    DeliveryEnvelope,
    DeliveryOutboxError,
    DeliveryStatus,
)

if TYPE_CHECKING:
    from datetime import datetime

    from iris.core.ids import LeaseId


def complete_delivery(
    item: DeliveryEnvelope,
    *,
    lease_id: LeaseId | None,
    result: ActionResult,
    completed_at: datetime,
) -> DeliveryEnvelope:
    """Leased deliveryをActionResultに対応する終端状態へ遷移する。

    Returns:
        lease情報を除去した終端DeliveryEnvelope。

    """
    _require_reportable_lease(item, lease_id)
    state = replace(
        _current_state(item),
        status=_delivery_status_from_action_status(result.status),
        updated_at=completed_at,
        lease_id=None,
        lease_expires_at=None,
        last_error_reason=result.error_reason,
    )
    return _rebuild_delivery(item, state)


def release_delivery(
    item: DeliveryEnvelope,
    *,
    lease_id: LeaseId | None,
    retry_after: datetime,
    result: ActionResult,
    released_at: datetime,
) -> DeliveryEnvelope:
    """Leased deliveryを再試行待ち、または恒久失敗へ遷移する。

    Returns:
        lease情報を除去したDeliveryEnvelope。

    """
    _require_reportable_lease(item, lease_id)
    if item.attempts >= item.max_attempts:
        state = replace(
            _current_state(item),
            status=DeliveryStatus.FAILED_PERMANENT,
            updated_at=released_at,
            lease_id=None,
            lease_expires_at=None,
            last_error_reason=result.error_reason,
        )
        return _rebuild_delivery(item, state)
    state = replace(
        _current_state(item),
        status=DeliveryStatus.PENDING,
        updated_at=released_at,
        not_before=retry_after,
        lease_id=None,
        lease_expires_at=None,
        last_error_reason=result.error_reason,
    )
    return _rebuild_delivery(item, state)


def fail_exhausted_delivery(
    item: DeliveryEnvelope,
    *,
    failed_at: datetime,
    error_reason: str,
) -> DeliveryEnvelope:
    """試行上限に達したdeliveryを恒久失敗へ遷移する。

    Returns:
        lease情報を除去したFAILED_PERMANENT envelope。
    """
    state = replace(
        _current_state(item),
        status=DeliveryStatus.FAILED_PERMANENT,
        updated_at=failed_at,
        lease_id=None,
        lease_expires_at=None,
        last_error_reason=error_reason,
    )
    return _rebuild_delivery(item, state)


def lease_delivery(
    item: DeliveryEnvelope,
    *,
    lease_id: LeaseId,
    leased_at: datetime,
    lease_seconds: float,
    not_before: datetime | None,
) -> DeliveryEnvelope:
    """Deliveryを指定lease IDでLEASEDへ遷移する。

    Returns:
        attemptsとlease期限を更新したDeliveryEnvelope。
    """
    state = replace(
        _current_state(item),
        status=DeliveryStatus.LEASED,
        updated_at=leased_at,
        not_before=not_before,
        attempts=item.attempts + 1,
        lease_id=lease_id,
        lease_expires_at=leased_at + timedelta(seconds=lease_seconds),
    )
    return _rebuild_delivery(item, state)


def is_delivery_due(item: DeliveryEnvelope, now: datetime) -> bool:
    """Delivery itemが現在lease可能か判定する。

    Returns:
        PENDINGかつ期限到来、または期限切れLEASEDならTrue。
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


@dataclass(frozen=True)
class _DeliveryState:
    status: DeliveryStatus
    updated_at: datetime
    not_before: datetime | None
    attempts: int
    lease_id: LeaseId | None
    lease_expires_at: datetime | None
    blocked_reason: str | None
    last_error_reason: str | None


def _current_state(item: DeliveryEnvelope) -> _DeliveryState:
    return _DeliveryState(
        status=item.status,
        updated_at=item.updated_at,
        not_before=item.not_before,
        attempts=item.attempts,
        lease_id=item.lease_id,
        lease_expires_at=item.lease_expires_at,
        blocked_reason=item.blocked_reason,
        last_error_reason=item.last_error_reason,
    )


def _rebuild_delivery(item: DeliveryEnvelope, state: _DeliveryState) -> DeliveryEnvelope:
    return DeliveryEnvelope(
        delivery_id=item.delivery_id,
        action=item.action,
        target=item.target,
        status=state.status,
        created_at=item.created_at,
        updated_at=state.updated_at,
        not_before=state.not_before,
        attempts=state.attempts,
        max_attempts=item.max_attempts,
        idempotency_key=item.idempotency_key,
        lease_id=state.lease_id,
        lease_expires_at=state.lease_expires_at,
        blocked_reason=state.blocked_reason,
        last_error_reason=state.last_error_reason,
    )


def _require_reportable_lease(
    item: DeliveryEnvelope,
    lease_id: LeaseId | None,
) -> None:
    if item.status in TERMINAL_DELIVERY_STATUSES:
        msg = "delivery_already_terminal"
        raise DeliveryOutboxError(msg)
    if item.status is not DeliveryStatus.LEASED:
        msg = "delivery_not_leased"
        raise DeliveryOutboxError(msg)
    if item.lease_id != lease_id:
        msg = "lease_mismatch"
        raise DeliveryOutboxError(msg)


def _delivery_status_from_action_status(status: ActionStatus) -> DeliveryStatus:
    if status is ActionStatus.SUCCEEDED:
        return DeliveryStatus.SUCCEEDED
    if status is ActionStatus.CANCELLED:
        return DeliveryStatus.CANCELLED
    if status is ActionStatus.BLOCKED:
        return DeliveryStatus.BLOCKED
    return DeliveryStatus.FAILED_PERMANENT
