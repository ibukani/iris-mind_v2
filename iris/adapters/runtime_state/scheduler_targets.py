"""SQLite-backed scheduler target store."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime
from pathlib import Path
import sqlite3
import threading
from typing import TYPE_CHECKING

from iris.contracts.delivery import DeliveryRouteHint, SchedulerTarget
from iris.core.ids import AccountId, ActorId, ExternalRef, SessionId, SpaceId

if TYPE_CHECKING:
    from collections.abc import Callable, Generator


class SQLiteSchedulerTargetStore:
    """SQLite-backed durable scheduler target store."""

    def __init__(self, sqlite_path: str) -> None:
        """Create a SQLite scheduler target store."""
        self._db_path = Path(sqlite_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = self._connect()
        self._init_schema()

    async def upsert_target(self, target: SchedulerTarget) -> None:
        """Insert or update a target by stable provider/session key."""
        await asyncio.to_thread(self._upsert_target_sync, target)

    async def list_targets(
        self,
        *,
        now: datetime,
    ) -> tuple[SchedulerTarget, ...]:
        """Return non-stale targets in deterministic order."""
        return await asyncio.to_thread(self._list_targets_sync, now)

    async def mark_scheduler_attempt(
        self,
        target: SchedulerTarget,
        *,
        attempted_at: datetime,
    ) -> None:
        """Update one target's scheduler attempt timestamp."""
        await asyncio.to_thread(self._mark_scheduler_attempt_sync, target, attempted_at)

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
        return conn

    def _init_schema(self) -> None:
        with self._locked_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduler_targets (
                    provider TEXT NOT NULL,
                    provider_subject TEXT NOT NULL,
                    provider_space_ref TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    actor_id TEXT,
                    account_id TEXT,
                    space_id TEXT,
                    display_name TEXT,
                    last_observed_at TEXT NOT NULL,
                    last_scheduler_attempt_at TEXT,
                    stale_after TEXT,
                    route_display_name TEXT,
                    PRIMARY KEY (
                        provider,
                        provider_subject,
                        provider_space_ref,
                        session_id
                    )
                )
                """
            )

    def _upsert_target_sync(self, target: SchedulerTarget) -> None:
        key = _target_key(target)
        with self._locked_connection() as conn:
            existing = conn.execute(
                """
                SELECT last_scheduler_attempt_at
                FROM scheduler_targets
                WHERE provider = ?
                  AND provider_subject = ?
                  AND provider_space_ref = ?
                  AND session_id = ?
                """,
                key,
            ).fetchone()
            last_attempt = (
                str(existing["last_scheduler_attempt_at"])
                if existing is not None and existing["last_scheduler_attempt_at"] is not None
                else _datetime_to_text(target.last_scheduler_attempt_at)
            )
            conn.execute(
                """
                INSERT INTO scheduler_targets (
                    provider,
                    provider_subject,
                    provider_space_ref,
                    session_id,
                    actor_id,
                    account_id,
                    space_id,
                    display_name,
                    last_observed_at,
                    last_scheduler_attempt_at,
                    stale_after,
                    route_display_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (
                    provider,
                    provider_subject,
                    provider_space_ref,
                    session_id
                ) DO UPDATE SET
                    actor_id = excluded.actor_id,
                    account_id = excluded.account_id,
                    space_id = excluded.space_id,
                    display_name = excluded.display_name,
                    last_observed_at = excluded.last_observed_at,
                    last_scheduler_attempt_at = ?,
                    stale_after = excluded.stale_after,
                    route_display_name = excluded.route_display_name
                """,
                (
                    *key,
                    _optional_text(target.actor_id),
                    _optional_text(target.account_id),
                    _optional_text(target.space_id),
                    target.display_name,
                    _required_datetime_to_text(target.last_observed_at),
                    last_attempt,
                    _datetime_to_text(target.stale_after),
                    target.route.display_name,
                    last_attempt,
                ),
            )

    def _list_targets_sync(self, now: datetime) -> tuple[SchedulerTarget, ...]:
        with self._locked_connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM scheduler_targets
                WHERE stale_after IS NULL OR stale_after > ?
                ORDER BY provider, provider_subject, provider_space_ref, session_id
                """,
                (_datetime_to_text(now),),
            ).fetchall()
        return tuple(_row_to_target(row) for row in rows)

    def _mark_scheduler_attempt_sync(
        self,
        target: SchedulerTarget,
        attempted_at: datetime,
    ) -> None:
        with self._locked_connection() as conn:
            conn.execute(
                """
                UPDATE scheduler_targets
                SET last_scheduler_attempt_at = ?
                WHERE provider = ?
                  AND provider_subject = ?
                  AND provider_space_ref = ?
                  AND session_id = ?
                """,
                (_datetime_to_text(attempted_at), *_target_key(target)),
            )

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


def _row_to_target(row: sqlite3.Row) -> SchedulerTarget:
    return SchedulerTarget(
        actor_id=_optional_new_type(ActorId, row["actor_id"]),
        account_id=_optional_new_type(AccountId, row["account_id"]),
        space_id=_optional_new_type(SpaceId, row["space_id"]),
        session_id=SessionId(str(row["session_id"])),
        route=DeliveryRouteHint(
            provider=str(row["provider"]),
            provider_subject=_empty_to_none(row["provider_subject"]),
            provider_space_ref=_empty_to_none(row["provider_space_ref"]),
            display_name=row["route_display_name"],
        ),
        display_name=row["display_name"],
        last_observed_at=_text_to_datetime(str(row["last_observed_at"])),
        last_scheduler_attempt_at=_optional_datetime(row["last_scheduler_attempt_at"]),
        stale_after=_optional_datetime(row["stale_after"]),
    )


def _target_key(target: SchedulerTarget) -> tuple[str, str, str, str]:
    return (
        target.route.provider,
        str(target.route.provider_subject or ""),
        str(target.route.provider_space_ref or ""),
        str(target.session_id),
    )


def _optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _empty_to_none(value: object) -> ExternalRef | None:
    text = str(value)
    if not text:
        return None
    return ExternalRef(text)


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
