"""SQLite-backed DeliveryOutbox implementation."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from enum import StrEnum
import json
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from iris.adapters.persistence.sqlite.context import (
    SQLiteDatabaseInput,
    resolve_database_manager,
)
from iris.adapters.persistence.sqlite.schema.delivery import (
    DeliveryOutboxModel,
    DeliveryReportFingerprintModel,
)
from iris.adapters.persistence.sqlite.serialization import (
    datetime_to_text,
    optional_datetime,
    optional_new_type,
    optional_text,
    required_datetime_to_text,
    text_to_datetime,
)
from iris.contracts.actions import ActionResult, NoAction, SendMessageAction
from iris.contracts.delivery import (
    TERMINAL_DELIVERY_STATUSES,
    DeliveryEnvelope,
    DeliveryOutboxError,
    DeliveryStatus,
    DeliveryTarget,
)
from iris.contracts.delivery_transitions import (
    complete_delivery,
    fail_exhausted_delivery,
    is_delivery_due,
    lease_delivery,
    release_delivery,
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
    from collections.abc import AsyncGenerator
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["SQLiteDeliveryOutbox"]


class SQLiteDeliveryOutbox:
    """Durable SQLite delivery outbox."""

    def __init__(
        self,
        db: SQLiteDatabaseInput,
        *,
        max_depth_per_provider: int | None = None,
    ) -> None:
        """Create a SQLite delivery outbox."""
        self._max_depth_per_provider = max_depth_per_provider
        self._db = resolve_database_manager(db)

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
                    if not is_delivery_due(item, now):
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
        """
        async with _map_operational_error(), self._db.transaction() as session:
            prepared = await _prepare_report(
                session,
                delivery_id=delivery_id,
                lease_id=lease_id,
                result=result,
            )
            if prepared.idempotent:
                return prepared.envelope
            completed = complete_delivery(
                prepared.envelope,
                lease_id=lease_id,
                result=result,
                completed_at=completed_at,
            )
            _update_model(prepared.model, completed)
            _insert_fingerprint(session, prepared.fingerprint)
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
        """
        async with _map_operational_error(), self._db.transaction() as session:
            prepared = await _prepare_report(
                session,
                delivery_id=delivery_id,
                lease_id=lease_id,
                result=result,
            )
            if prepared.idempotent:
                return prepared.envelope
            released = release_delivery(
                prepared.envelope,
                lease_id=lease_id,
                retry_after=retry_after,
                result=result,
                released_at=released_at,
            )
            _update_model(prepared.model, released)
            _insert_fingerprint(session, prepared.fingerprint)
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


@dataclass(frozen=True)
class _PreparedReport:
    model: DeliveryOutboxModel
    envelope: DeliveryEnvelope
    fingerprint: _ReportFingerprint
    idempotent: bool


def _lease_item(
    item: DeliveryEnvelope,
    *,
    now: datetime,
    lease_seconds: float,
) -> DeliveryEnvelope:
    if item.attempts >= item.max_attempts:
        return fail_exhausted_delivery(
            item,
            failed_at=now,
            error_reason=item.last_error_reason or "max_attempts_exceeded",
        )
    attempt = item.attempts + 1
    return lease_delivery(
        item,
        lease_id=LeaseId(f"{item.delivery_id}:lease:{attempt}"),
        leased_at=now,
        lease_seconds=lease_seconds,
        not_before=None,
    )


def _update_model(model: DeliveryOutboxModel, envelope: DeliveryEnvelope) -> None:
    model.status = envelope.status.value
    model.updated_at = required_datetime_to_text(envelope.updated_at)
    model.not_before = datetime_to_text(envelope.not_before)
    model.attempts = envelope.attempts
    model.max_attempts = envelope.max_attempts
    model.lease_id = optional_text(envelope.lease_id)
    model.lease_expires_at = datetime_to_text(envelope.lease_expires_at)
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


async def _prepare_report(
    session: AsyncSession,
    *,
    delivery_id: DeliveryId,
    lease_id: LeaseId | None,
    result: ActionResult,
) -> _PreparedReport:
    model = await session.scalar(
        select(DeliveryOutboxModel).where(
            DeliveryOutboxModel.delivery_id == str(delivery_id)
        )
    )
    if model is None:
        msg = "delivery_not_found"
        raise DeliveryOutboxError(msg)
    fingerprint = _result_fingerprint(delivery_id, lease_id, result)
    outcome = await _classify_report(session, fingerprint)
    if outcome is _ReportOutcome.CONFLICT:
        msg = "delivery_report_conflict"
        raise DeliveryOutboxError(msg)
    return _PreparedReport(
        model=model,
        envelope=_model_to_envelope(model),
        fingerprint=fingerprint,
        idempotent=outcome is _ReportOutcome.IDEMPOTENT,
    )


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
            DeliveryReportFingerprintModel.lease_id == optional_text(current.lease_id),
        )
    )
    if conflict is not None:
        return _ReportOutcome.CONFLICT
    return _ReportOutcome.NEW


def _insert_fingerprint(session: AsyncSession, fingerprint: _ReportFingerprint) -> None:
    model = DeliveryReportFingerprintModel(
        fingerprint_key=_build_fingerprint_key(fingerprint),
        delivery_id=str(fingerprint.delivery_id),
        lease_id=optional_text(fingerprint.lease_id),
        action_id=str(fingerprint.action_id),
        correlation_id=str(fingerprint.correlation_id),
        status=fingerprint.status,
        external_message_id=optional_text(fingerprint.external_message_id),
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


def _envelope_to_model(envelope: DeliveryEnvelope) -> DeliveryOutboxModel:
    action = envelope.action
    if not isinstance(action, SendMessageAction):
        msg = "unsupported_delivery_action"
        raise DeliveryOutboxError(msg)
    return DeliveryOutboxModel(
        delivery_id=str(envelope.delivery_id),
        idempotency_key=envelope.idempotency_key,
        status=envelope.status.value,
        created_at=required_datetime_to_text(envelope.created_at),
        updated_at=required_datetime_to_text(envelope.updated_at),
        not_before=datetime_to_text(envelope.not_before),
        attempts=envelope.attempts,
        max_attempts=envelope.max_attempts,
        lease_id=optional_text(envelope.lease_id),
        lease_expires_at=datetime_to_text(envelope.lease_expires_at),
        blocked_reason=envelope.blocked_reason,
        last_error_reason=envelope.last_error_reason,
        target_provider=envelope.target.provider,
        target_provider_subject=optional_text(envelope.target.provider_subject),
        target_provider_space_ref=optional_text(envelope.target.provider_space_ref),
        target_session_id=str(envelope.target.session_id),
        target_actor_id=optional_text(envelope.target.actor_id),
        target_account_id=optional_text(envelope.target.account_id),
        target_space_id=optional_text(envelope.target.space_id),
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
            provider_subject=optional_new_type(
                ExternalRef,
                row.target_provider_subject,
            ),
            provider_space_ref=optional_new_type(
                ExternalRef,
                row.target_provider_space_ref,
            ),
            session_id=SessionId(str(row.target_session_id)),
            actor_id=optional_new_type(ActorId, row.target_actor_id),
            account_id=optional_new_type(AccountId, row.target_account_id),
            space_id=optional_new_type(SpaceId, row.target_space_id),
        ),
        status=DeliveryStatus(str(row.status)),
        created_at=text_to_datetime(str(row.created_at)),
        updated_at=text_to_datetime(str(row.updated_at)),
        not_before=optional_datetime(row.not_before),
        attempts=int(row.attempts),
        max_attempts=int(row.max_attempts),
        idempotency_key=str(row.idempotency_key),
        lease_id=optional_new_type(LeaseId, row.lease_id),
        lease_expires_at=optional_datetime(row.lease_expires_at),
        blocked_reason=row.blocked_reason,
        last_error_reason=row.last_error_reason,
    )
