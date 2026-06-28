"""SQLite-backed DeliveryOutbox implementation."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
import json
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from iris.adapters.persistence.sqlite.engine import AsyncDatabaseManager
from iris.adapters.persistence.sqlite.schema.delivery import (
    DeliveryOutboxModel,
    DeliveryReportFingerprintModel,
)
from iris.contracts.actions import ActionResult, ActionStatus, NoAction, SendMessageAction
from iris.contracts.delivery import (
    TERMINAL_DELIVERY_STATUSES,
    DeliveryEnvelope,
    DeliveryOutboxError,
    DeliveryStatus,
    DeliveryTarget,
)
from iris.core.ids import (
    AccountId,
    ActionId,
    ActorId,
    CorrelationId,
    DeliveryId,
    ExternalRef,
    LeaseId,
    SessionId,
    SpaceId,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["SQLiteDeliveryOutbox"]


class SQLiteDeliveryOutbox:
    """Durable SQLite delivery outbox."""

    def __init__(
        self, sqlite_path: str | Path, *, max_depth_per_provider: int | None = None
    ) -> None:
        """Create a SQLite delivery outbox."""
        self._max_depth_per_provider = max_depth_per_provider
        self._db = AsyncDatabaseManager(sqlite_path)

    async def enqueue(self, envelope: DeliveryEnvelope) -> DeliveryEnvelope:
        """Store pending delivery item idempotently by idempotency key.

        Returns:
            Stored envelope, or existing envelope for repeated idempotency key.

        Raises:
            DeliveryOutboxError: On backend error or validation failure.
        """
        if isinstance(envelope.action, NoAction):
            msg = "no_action_not_deliverable"
            raise DeliveryOutboxError(msg)
        if not envelope.idempotency_key:
            msg = "idempotency_key_required"
            raise DeliveryOutboxError(msg)

        async with _map_operational_error(), self._db.transaction() as session:
            existing = await session.scalar(
                select(DeliveryOutboxModel).where(
                    DeliveryOutboxModel.idempotency_key == envelope.idempotency_key
                )
            )
            if existing is not None:
                return _model_to_envelope(existing)

            if await self._depth_exceeded(session, envelope.target.provider):
                msg = "outbox_depth_exceeded"
                raise DeliveryOutboxError(msg)

            model = _envelope_to_model(envelope)
            session.add(model)
            return envelope

    async def _depth_exceeded(self, session: AsyncSession, provider: str) -> bool:
        if self._max_depth_per_provider is None:
            return False
        terminal_values = tuple(status.value for status in TERMINAL_DELIVERY_STATUSES)
        active_count = await session.scalar(
            select(func.count())
            .select_from(DeliveryOutboxModel)
            .where(
                DeliveryOutboxModel.target_provider == provider,
                DeliveryOutboxModel.status.notin_(terminal_values),
            )
        )
        return int(active_count or 0) >= self._max_depth_per_provider

    async def lease_due(
        self,
        *,
        provider: str,
        now: datetime,
        max_items: int,
        lease_seconds: float,
    ) -> tuple[DeliveryEnvelope, ...]:
        """Lease due items for a provider.

        Returns:
            Leased envelopes in deterministic created-at order.
        """
        due: list[DeliveryEnvelope] = []
        async with _map_operational_error():
            async with self._db.transaction() as session:
                result = await session.scalars(
                    select(DeliveryOutboxModel)
                    .where(
                        DeliveryOutboxModel.target_provider == provider,
                        DeliveryOutboxModel.status.in_(
                            [DeliveryStatus.PENDING.value, DeliveryStatus.LEASED.value]
                        ),
                    )
                    .order_by(DeliveryOutboxModel.created_at, DeliveryOutboxModel.delivery_id)
                )
                rows = result.all()
                for row in rows:
                    if len(due) >= max_items:
                        break
                    item = _model_to_envelope(row)
                    if not _is_due(item, now):
                        continue
                    leased = _lease_item(item, now=now, lease_seconds=lease_seconds)
                    _update_model(row, leased)
                    if leased.status is DeliveryStatus.LEASED:
                        due.append(leased)
            return tuple(due)

    async def get(self, delivery_id: DeliveryId) -> DeliveryEnvelope:
        """Return delivery envelope without mutating state.

        Raises:
            DeliveryOutboxError: On backend error or not found.
        """
        async with _map_operational_error():
            async with self._db.transaction() as session:
                row = await session.scalar(
                    select(DeliveryOutboxModel).where(
                        DeliveryOutboxModel.delivery_id == str(delivery_id)
                    )
                )
            if row is None:
                msg = "delivery_not_found"
                raise DeliveryOutboxError(msg)
            return _model_to_envelope(row)

    async def complete(
        self,
        *,
        delivery_id: DeliveryId,
        lease_id: LeaseId | None,
        result: ActionResult,
        completed_at: datetime,
    ) -> DeliveryEnvelope:
        """Complete leased item with idempotent report handling.

        Returns:
            Updated terminal envelope, or existing envelope for repeated report.

        Raises:
            DeliveryOutboxError: On backend error, conflicts, or not found.
        """
        async with _map_operational_error(), self._db.transaction() as session:
            row = await session.scalar(
                select(DeliveryOutboxModel).where(
                    DeliveryOutboxModel.delivery_id == str(delivery_id)
                )
            )
            if row is None:
                msg = "delivery_not_found"
                raise DeliveryOutboxError(msg)
            item = _model_to_envelope(row)
            current = _result_fingerprint(delivery_id, lease_id, result)
            outcome = await _classify_report(session, current)
            if outcome is _ReportOutcome.IDEMPOTENT:
                return item
            if outcome is _ReportOutcome.CONFLICT:
                msg = "delivery_report_conflict"
                raise DeliveryOutboxError(msg)
            if item.status in TERMINAL_DELIVERY_STATUSES:
                msg = "delivery_already_terminal"
                raise DeliveryOutboxError(msg)
            _require_matching_lease(item, lease_id)
            completed = replace(
                item,
                status=_delivery_status_from_action_status(result.status),
                updated_at=completed_at,
                lease_id=None,
                lease_expires_at=None,
                last_error_reason=result.error_reason,
            )
            _update_model(row, completed)
            _insert_fingerprint(session, current)
            return completed

    async def release(
        self,
        *,
        delivery_id: DeliveryId,
        lease_id: LeaseId | None,
        retry_after: datetime,
        result: ActionResult,
        released_at: datetime,
    ) -> DeliveryEnvelope:
        """Release leased item for retry or permanent failure.

        Returns:
            Updated pending or permanently failed envelope.

        Raises:
            DeliveryOutboxError: On backend error, conflicts, or not found.
        """
        async with _map_operational_error(), self._db.transaction() as session:
            row = await session.scalar(
                select(DeliveryOutboxModel).where(
                    DeliveryOutboxModel.delivery_id == str(delivery_id)
                )
            )
            if row is None:
                msg = "delivery_not_found"
                raise DeliveryOutboxError(msg)
            item = _model_to_envelope(row)
            current = _result_fingerprint(delivery_id, lease_id, result)
            outcome = await _classify_report(session, current)
            if outcome is _ReportOutcome.IDEMPOTENT:
                return item
            if outcome is _ReportOutcome.CONFLICT:
                msg = "delivery_report_conflict"
                raise DeliveryOutboxError(msg)
            if item.status in TERMINAL_DELIVERY_STATUSES:
                msg = "delivery_already_terminal"
                raise DeliveryOutboxError(msg)
            _require_matching_lease(item, lease_id)
            if item.attempts >= item.max_attempts:
                released = replace(
                    item,
                    status=DeliveryStatus.FAILED_PERMANENT,
                    updated_at=released_at,
                    lease_id=None,
                    lease_expires_at=None,
                    last_error_reason=result.error_reason,
                )
            else:
                released = replace(
                    item,
                    status=DeliveryStatus.PENDING,
                    updated_at=released_at,
                    not_before=retry_after,
                    lease_id=None,
                    lease_expires_at=None,
                    last_error_reason=result.error_reason,
                )
            _update_model(row, released)
            _insert_fingerprint(session, current)
            return released

    async def close(self) -> None:
        """Close the underlying SQLite connection."""
        await self._db.close()


@contextlib.asynccontextmanager
async def _map_operational_error() -> AsyncGenerator[None]:
    try:
        yield
    except OperationalError as exc:
        reason = (
            "delivery_backend_unavailable"
            if "database is locked" in str(exc).lower() or "busy" in str(exc).lower()
            else "delivery_backend_error"
        )
        raise DeliveryOutboxError(reason) from exc


class _ReportOutcome(StrEnum):
    IDEMPOTENT = "idempotent"
    CONFLICT = "conflict"
    NEW = "new"


def _lease_item(
    item: DeliveryEnvelope,
    *,
    now: datetime,
    lease_seconds: float,
) -> DeliveryEnvelope:
    if item.attempts >= item.max_attempts:
        return replace(
            item,
            status=DeliveryStatus.FAILED_PERMANENT,
            updated_at=now,
            lease_id=None,
            lease_expires_at=None,
            last_error_reason=item.last_error_reason or "max_attempts_exceeded",
        )
    attempt = item.attempts + 1
    return replace(
        item,
        status=DeliveryStatus.LEASED,
        updated_at=now,
        not_before=None,
        attempts=attempt,
        lease_id=LeaseId(f"{item.delivery_id}:lease:{attempt}"),
        lease_expires_at=now + timedelta(seconds=lease_seconds),
    )


def _update_model(model: DeliveryOutboxModel, envelope: DeliveryEnvelope) -> None:
    model.status = envelope.status.value
    model.updated_at = _required_datetime_to_text(envelope.updated_at)
    model.not_before = _datetime_to_text(envelope.not_before)
    model.attempts = envelope.attempts
    model.max_attempts = envelope.max_attempts
    model.lease_id = _optional_text(envelope.lease_id)
    model.lease_expires_at = _datetime_to_text(envelope.lease_expires_at)
    model.blocked_reason = envelope.blocked_reason
    model.last_error_reason = envelope.last_error_reason


@dataclass(frozen=True)
class _ReportFingerprint:
    delivery_id: DeliveryId
    lease_id: LeaseId | None
    action_id: ActionId
    correlation_id: CorrelationId
    status: str
    external_message_id: ExternalRef | None
    error_reason: str | None


def _build_fingerprint_key(fingerprint: _ReportFingerprint) -> str:
    return json.dumps(
        {
            "delivery_id": str(fingerprint.delivery_id),
            "lease_id": str(fingerprint.lease_id) if fingerprint.lease_id else None,
            "action_id": str(fingerprint.action_id),
            "correlation_id": str(fingerprint.correlation_id),
            "status": fingerprint.status,
            "external_message_id": (
                str(fingerprint.external_message_id) if fingerprint.external_message_id else None
            ),
            "error_reason": fingerprint.error_reason,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


async def _classify_report(
    session: AsyncSession,
    current: _ReportFingerprint,
) -> _ReportOutcome:
    fingerprint_key = _build_fingerprint_key(current)
    exact = await session.scalar(
        select(DeliveryReportFingerprintModel).where(
            DeliveryReportFingerprintModel.fingerprint_key == fingerprint_key
        )
    )
    if exact is not None:
        return _ReportOutcome.IDEMPOTENT
    conflict = await session.scalar(
        select(DeliveryReportFingerprintModel).where(
            DeliveryReportFingerprintModel.delivery_id == str(current.delivery_id),
            DeliveryReportFingerprintModel.lease_id == _optional_text(current.lease_id),
        )
    )
    if conflict is not None:
        return _ReportOutcome.CONFLICT
    return _ReportOutcome.NEW


def _insert_fingerprint(session: AsyncSession, fingerprint: _ReportFingerprint) -> None:
    model = DeliveryReportFingerprintModel(
        fingerprint_key=_build_fingerprint_key(fingerprint),
        delivery_id=str(fingerprint.delivery_id),
        lease_id=_optional_text(fingerprint.lease_id),
        action_id=str(fingerprint.action_id),
        correlation_id=str(fingerprint.correlation_id),
        status=fingerprint.status,
        external_message_id=_optional_text(fingerprint.external_message_id),
        error_reason=fingerprint.error_reason,
    )
    session.add(model)


def _result_fingerprint(
    delivery_id: DeliveryId,
    lease_id: LeaseId | None,
    result: ActionResult,
) -> _ReportFingerprint:
    return _ReportFingerprint(
        delivery_id=delivery_id,
        lease_id=lease_id,
        action_id=result.action_id,
        correlation_id=result.correlation_id,
        status=result.status.value,
        external_message_id=result.external_message_id,
        error_reason=result.error_reason,
    )


def _is_due(item: DeliveryEnvelope, now: datetime) -> bool:
    if item.status is DeliveryStatus.PENDING:
        return item.not_before is None or item.not_before <= now
    if item.status is DeliveryStatus.LEASED:
        return item.lease_expires_at is not None and item.lease_expires_at <= now
    return False


def _require_matching_lease(item: DeliveryEnvelope, lease_id: LeaseId | None) -> None:
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


def _envelope_to_model(envelope: DeliveryEnvelope) -> DeliveryOutboxModel:
    action = envelope.action
    if not isinstance(action, SendMessageAction):
        msg = "unsupported_delivery_action"
        raise DeliveryOutboxError(msg)
    return DeliveryOutboxModel(
        delivery_id=str(envelope.delivery_id),
        idempotency_key=envelope.idempotency_key,
        status=envelope.status.value,
        created_at=_required_datetime_to_text(envelope.created_at),
        updated_at=_required_datetime_to_text(envelope.updated_at),
        not_before=_datetime_to_text(envelope.not_before),
        attempts=envelope.attempts,
        max_attempts=envelope.max_attempts,
        lease_id=_optional_text(envelope.lease_id),
        lease_expires_at=_datetime_to_text(envelope.lease_expires_at),
        blocked_reason=envelope.blocked_reason,
        last_error_reason=envelope.last_error_reason,
        target_provider=envelope.target.provider,
        target_provider_subject=_optional_text(envelope.target.provider_subject),
        target_provider_space_ref=_optional_text(envelope.target.provider_space_ref),
        target_session_id=str(envelope.target.session_id),
        target_actor_id=_optional_text(envelope.target.actor_id),
        target_account_id=_optional_text(envelope.target.account_id),
        target_space_id=_optional_text(envelope.target.space_id),
        action_type="send_message",
        action_id=str(action.action_id),
        action_session_id=str(action.session_id),
        action_correlation_id=str(action.correlation_id),
        action_text=action.text,
    )


def _model_to_envelope(row: DeliveryOutboxModel) -> DeliveryEnvelope:
    return DeliveryEnvelope(
        delivery_id=DeliveryId(str(row.delivery_id)),
        action=SendMessageAction(
            action_id=ActionId(str(row.action_id)),
            session_id=SessionId(str(row.action_session_id)),
            correlation_id=CorrelationId(str(row.action_correlation_id)),
            text=str(row.action_text),
        ),
        target=DeliveryTarget(
            provider=str(row.target_provider),
            provider_subject=_optional_new_type(
                ExternalRef,
                row.target_provider_subject,
            ),
            provider_space_ref=_optional_new_type(
                ExternalRef,
                row.target_provider_space_ref,
            ),
            session_id=SessionId(str(row.target_session_id)),
            actor_id=_optional_new_type(ActorId, row.target_actor_id),
            account_id=_optional_new_type(AccountId, row.target_account_id),
            space_id=_optional_new_type(SpaceId, row.target_space_id),
        ),
        status=DeliveryStatus(str(row.status)),
        created_at=_text_to_datetime(str(row.created_at)),
        updated_at=_text_to_datetime(str(row.updated_at)),
        not_before=_optional_datetime(row.not_before),
        attempts=int(row.attempts),
        max_attempts=int(row.max_attempts),
        idempotency_key=str(row.idempotency_key),
        lease_id=_optional_new_type(LeaseId, row.lease_id),
        lease_expires_at=_optional_datetime(row.lease_expires_at),
        blocked_reason=row.blocked_reason,
        last_error_reason=row.last_error_reason,
    )


def _optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_new_type[IdT: str](
    type_constructor: Callable[[str], IdT],
    value: object | None,
) -> IdT | None:
    if value is None:
        return None
    return type_constructor(str(value))


def _datetime_to_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _required_datetime_to_text(value: datetime) -> str:
    return value.isoformat()


def _text_to_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _optional_datetime(value: object | None) -> datetime | None:
    if value is None:
        return None
    return _text_to_datetime(str(value))
