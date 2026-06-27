"""SQLite-backed DeliveryOutbox implementation."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
import json
from pathlib import Path
import sqlite3
import threading
from typing import TYPE_CHECKING

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
    from collections.abc import Callable, Generator

__all__ = ["SQLiteDeliveryOutbox"]


class SQLiteDeliveryOutbox:
    """Durable SQLite delivery outbox."""

    def __init__(self, sqlite_path: str, *, max_depth_per_provider: int | None = None) -> None:
        """Create a SQLite delivery outbox."""
        self._db_path = Path(sqlite_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._max_depth_per_provider = max_depth_per_provider
        self._lock = threading.RLock()
        self._conn = self._connect()
        self._init_schema()

    async def enqueue(self, envelope: DeliveryEnvelope) -> DeliveryEnvelope:
        """Store pending delivery item idempotently by idempotency key.

        Returns:
            Stored envelope, or existing envelope for repeated idempotency key.
        """
        return await asyncio.to_thread(self._enqueue_sync, envelope)

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
        return await asyncio.to_thread(
            self._lease_due_sync,
            provider,
            now,
            max_items,
            lease_seconds,
        )

    async def get(self, delivery_id: DeliveryId) -> DeliveryEnvelope:
        """Return delivery envelope without mutating state."""
        return await asyncio.to_thread(self._get, delivery_id)

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
        return await asyncio.to_thread(
            self._complete_sync,
            delivery_id,
            lease_id,
            result,
            completed_at,
        )

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
        return await asyncio.to_thread(
            self._release_sync,
            delivery_id,
            lease_id,
            retry_after,
            result,
            released_at,
        )

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        with self._lock:
            self._conn.close()

    def __del__(self) -> None:
        """Close the SQLite connection during garbage collection."""
        with contextlib.suppress(sqlite3.Error):
            self.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _init_schema(self) -> None:
        with self._locked_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS delivery_outbox (
                    delivery_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    not_before TEXT,
                    attempts INTEGER NOT NULL,
                    max_attempts INTEGER NOT NULL,
                    lease_id TEXT,
                    lease_expires_at TEXT,
                    blocked_reason TEXT,
                    last_error_reason TEXT,
                    target_provider TEXT NOT NULL,
                    target_provider_subject TEXT,
                    target_provider_space_ref TEXT,
                    target_session_id TEXT NOT NULL,
                    target_actor_id TEXT,
                    target_account_id TEXT,
                    target_space_id TEXT,
                    action_type TEXT NOT NULL,
                    action_id TEXT NOT NULL,
                    action_session_id TEXT NOT NULL,
                    action_correlation_id TEXT NOT NULL,
                    action_text TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS delivery_report_fingerprints (
                    fingerprint_key TEXT PRIMARY KEY,
                    delivery_id TEXT NOT NULL,
                    lease_id TEXT,
                    action_id TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    external_message_id TEXT,
                    error_reason TEXT,
                    FOREIGN KEY (delivery_id)
                        REFERENCES delivery_outbox(delivery_id)
                        ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS delivery_outbox_due_idx
                ON delivery_outbox (
                    target_provider,
                    status,
                    created_at,
                    delivery_id
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS delivery_report_lease_idx
                ON delivery_report_fingerprints (delivery_id, lease_id)
                """
            )

    def _enqueue_sync(self, envelope: DeliveryEnvelope) -> DeliveryEnvelope:
        if isinstance(envelope.action, NoAction):
            msg = "no_action_not_deliverable"
            raise DeliveryOutboxError(msg)
        if not envelope.idempotency_key:
            msg = "idempotency_key_required"
            raise DeliveryOutboxError(msg)
        with self._immediate_transaction() as conn:
            existing = conn.execute(
                """
                SELECT *
                FROM delivery_outbox
                WHERE idempotency_key = ?
                """,
                (envelope.idempotency_key,),
            ).fetchone()
            if existing is not None:
                return _row_to_envelope(existing)
            if self._depth_exceeded(conn, envelope.target.provider):
                msg = "outbox_depth_exceeded"
                raise DeliveryOutboxError(msg)
            conn.execute(
                """
                INSERT INTO delivery_outbox (
                    delivery_id,
                    idempotency_key,
                    status,
                    created_at,
                    updated_at,
                    not_before,
                    attempts,
                    max_attempts,
                    lease_id,
                    lease_expires_at,
                    blocked_reason,
                    last_error_reason,
                    target_provider,
                    target_provider_subject,
                    target_provider_space_ref,
                    target_session_id,
                    target_actor_id,
                    target_account_id,
                    target_space_id,
                    action_type,
                    action_id,
                    action_session_id,
                    action_correlation_id,
                    action_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _envelope_params(envelope),
            )
        return envelope

    def _depth_exceeded(self, conn: sqlite3.Connection, provider: str) -> bool:
        if self._max_depth_per_provider is None:
            return False
        terminal_values = tuple(status.value for status in TERMINAL_DELIVERY_STATUSES)
        active_count = conn.execute(
            """
            SELECT COUNT(*) AS active_count
            FROM delivery_outbox
            WHERE target_provider = ?
              AND status NOT IN (?, ?, ?, ?)
            """,
            (provider, *terminal_values),
        ).fetchone()
        return int(active_count["active_count"]) >= self._max_depth_per_provider

    def _lease_due_sync(
        self,
        provider: str,
        now: datetime,
        max_items: int,
        lease_seconds: float,
    ) -> tuple[DeliveryEnvelope, ...]:
        due: list[DeliveryEnvelope] = []
        with self._immediate_transaction() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM delivery_outbox
                WHERE target_provider = ?
                  AND status IN (?, ?)
                ORDER BY created_at, delivery_id
                """,
                (provider, DeliveryStatus.PENDING.value, DeliveryStatus.LEASED.value),
            ).fetchall()
            for row in rows:
                if len(due) >= max_items:
                    break
                item = _row_to_envelope(row)
                if not _is_due(item, now):
                    continue
                leased = _lease_item(item, now=now, lease_seconds=lease_seconds)
                _store_envelope(conn, leased)
                if leased.status is DeliveryStatus.LEASED:
                    due.append(leased)
        return tuple(due)

    def _get(self, delivery_id: DeliveryId) -> DeliveryEnvelope:
        with self._locked_connection() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM delivery_outbox
                WHERE delivery_id = ?
                """,
                (str(delivery_id),),
            ).fetchone()
        if row is None:
            msg = "delivery_not_found"
            raise DeliveryOutboxError(msg)
        return _row_to_envelope(row)

    def _complete_sync(
        self,
        delivery_id: DeliveryId,
        lease_id: LeaseId | None,
        result: ActionResult,
        completed_at: datetime,
    ) -> DeliveryEnvelope:
        with self._immediate_transaction() as conn:
            item = _get_for_update(conn, delivery_id)
            current = _result_fingerprint(delivery_id, lease_id, result)
            outcome = _classify_report(conn, current)
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
            _store_envelope(conn, completed)
            _insert_fingerprint(conn, current)
            return completed

    def _release_sync(
        self,
        delivery_id: DeliveryId,
        lease_id: LeaseId | None,
        retry_after: datetime,
        result: ActionResult,
        released_at: datetime,
    ) -> DeliveryEnvelope:
        with self._immediate_transaction() as conn:
            item = _get_for_update(conn, delivery_id)
            current = _result_fingerprint(delivery_id, lease_id, result)
            outcome = _classify_report(conn, current)
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
            _store_envelope(conn, released)
            _insert_fingerprint(conn, current)
            return released

    @contextlib.contextmanager
    def _locked_connection(self) -> Generator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._conn
            except BaseException:
                self._conn.rollback()
                raise
            else:
                self._conn.commit()

    @contextlib.contextmanager
    def _immediate_transaction(self) -> Generator[sqlite3.Connection]:
        txn_active = False
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                txn_active = True
                yield self._conn
                self._conn.commit()
            except sqlite3.OperationalError as exc:
                if txn_active:
                    with contextlib.suppress(sqlite3.OperationalError):
                        self._conn.execute("ROLLBACK")
                if not txn_active and ("database is locked" in str(exc) or "busy" in str(exc)):
                    msg = "delivery_backend_unavailable"
                    raise DeliveryOutboxError(msg) from exc
                raise
            except Exception:
                if txn_active:
                    with contextlib.suppress(sqlite3.OperationalError):
                        self._conn.execute("ROLLBACK")
                raise


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


def _get_for_update(
    conn: sqlite3.Connection,
    delivery_id: DeliveryId,
) -> DeliveryEnvelope:
    row = conn.execute(
        """
        SELECT *
        FROM delivery_outbox
        WHERE delivery_id = ?
        """,
        (str(delivery_id),),
    ).fetchone()
    if row is None:
        msg = "delivery_not_found"
        raise DeliveryOutboxError(msg)
    return _row_to_envelope(row)


def _store_envelope(
    conn: sqlite3.Connection,
    envelope: DeliveryEnvelope,
) -> None:
    conn.execute(
        """
        UPDATE delivery_outbox
        SET status = ?,
            updated_at = ?,
            not_before = ?,
            attempts = ?,
            max_attempts = ?,
            lease_id = ?,
            lease_expires_at = ?,
            blocked_reason = ?,
            last_error_reason = ?
        WHERE delivery_id = ?
        """,
        (
            envelope.status.value,
            _datetime_to_text(envelope.updated_at),
            _datetime_to_text(envelope.not_before),
            envelope.attempts,
            envelope.max_attempts,
            _optional_text(envelope.lease_id),
            _datetime_to_text(envelope.lease_expires_at),
            envelope.blocked_reason,
            envelope.last_error_reason,
            str(envelope.delivery_id),
        ),
    )


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


def _classify_report(
    conn: sqlite3.Connection,
    current: _ReportFingerprint,
) -> _ReportOutcome:
    fingerprint_key = _build_fingerprint_key(current)
    exact = conn.execute(
        """
        SELECT 1
        FROM delivery_report_fingerprints
        WHERE fingerprint_key = ?
        """,
        (fingerprint_key,),
    ).fetchone()
    if exact is not None:
        return _ReportOutcome.IDEMPOTENT
    conflict = conn.execute(
        """
        SELECT 1
        FROM delivery_report_fingerprints
        WHERE delivery_id = ?
          AND lease_id IS ?
        """,
        (str(current.delivery_id), _optional_text(current.lease_id)),
    ).fetchone()
    if conflict is not None:
        return _ReportOutcome.CONFLICT
    return _ReportOutcome.NEW


def _insert_fingerprint(conn: sqlite3.Connection, fingerprint: _ReportFingerprint) -> None:
    conn.execute(
        """
        INSERT INTO delivery_report_fingerprints (
            fingerprint_key,
            delivery_id,
            lease_id,
            action_id,
            correlation_id,
            status,
            external_message_id,
            error_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _build_fingerprint_key(fingerprint),
            str(fingerprint.delivery_id),
            _optional_text(fingerprint.lease_id),
            str(fingerprint.action_id),
            str(fingerprint.correlation_id),
            fingerprint.status,
            _optional_text(fingerprint.external_message_id),
            fingerprint.error_reason,
        ),
    )


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


def _envelope_params(
    envelope: DeliveryEnvelope,
) -> tuple[
    str,
    str,
    str,
    str,
    str,
    str | None,
    int,
    int,
    str | None,
    str | None,
    str | None,
    str | None,
    str,
    str | None,
    str | None,
    str,
    str | None,
    str | None,
    str | None,
    str,
    str,
    str,
    str,
    str,
]:
    action = envelope.action
    if not isinstance(action, SendMessageAction):
        msg = "unsupported_delivery_action"
        raise DeliveryOutboxError(msg)
    return (
        str(envelope.delivery_id),
        envelope.idempotency_key,
        envelope.status.value,
        _required_datetime_to_text(envelope.created_at),
        _required_datetime_to_text(envelope.updated_at),
        _datetime_to_text(envelope.not_before),
        envelope.attempts,
        envelope.max_attempts,
        _optional_text(envelope.lease_id),
        _datetime_to_text(envelope.lease_expires_at),
        envelope.blocked_reason,
        envelope.last_error_reason,
        envelope.target.provider,
        _optional_text(envelope.target.provider_subject),
        _optional_text(envelope.target.provider_space_ref),
        str(envelope.target.session_id),
        _optional_text(envelope.target.actor_id),
        _optional_text(envelope.target.account_id),
        _optional_text(envelope.target.space_id),
        "send_message",
        str(action.action_id),
        str(action.session_id),
        str(action.correlation_id),
        action.text,
    )


def _row_to_envelope(row: sqlite3.Row) -> DeliveryEnvelope:
    return DeliveryEnvelope(
        delivery_id=DeliveryId(str(row["delivery_id"])),
        action=SendMessageAction(
            action_id=ActionId(str(row["action_id"])),
            session_id=SessionId(str(row["action_session_id"])),
            correlation_id=CorrelationId(str(row["action_correlation_id"])),
            text=str(row["action_text"]),
        ),
        target=DeliveryTarget(
            provider=str(row["target_provider"]),
            provider_subject=_optional_new_type(
                ExternalRef,
                row["target_provider_subject"],
            ),
            provider_space_ref=_optional_new_type(
                ExternalRef,
                row["target_provider_space_ref"],
            ),
            session_id=SessionId(str(row["target_session_id"])),
            actor_id=_optional_new_type(ActorId, row["target_actor_id"]),
            account_id=_optional_new_type(AccountId, row["target_account_id"]),
            space_id=_optional_new_type(SpaceId, row["target_space_id"]),
        ),
        status=DeliveryStatus(str(row["status"])),
        created_at=_text_to_datetime(str(row["created_at"])),
        updated_at=_text_to_datetime(str(row["updated_at"])),
        not_before=_optional_datetime(row["not_before"]),
        attempts=int(row["attempts"]),
        max_attempts=int(row["max_attempts"]),
        idempotency_key=str(row["idempotency_key"]),
        lease_id=_optional_new_type(LeaseId, row["lease_id"]),
        lease_expires_at=_optional_datetime(row["lease_expires_at"]),
        blocked_reason=row["blocked_reason"],
        last_error_reason=row["last_error_reason"],
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
