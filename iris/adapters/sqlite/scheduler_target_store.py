"""SQLite-backed scheduler target store."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from iris.adapters.sqlite.engine import AsyncDatabaseManager
from iris.adapters.sqlite.models.scheduler_target import SchedulerTargetModel
from iris.contracts.delivery import DeliveryRouteHint, SchedulerTarget
from iris.core.ids import AccountId, ActorId, ExternalRef, SessionId, SpaceId

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


class SQLiteSchedulerTargetStore:
    """SQLite-backed durable scheduler target store."""

    def __init__(self, sqlite_path: str | Path) -> None:
        """Create a SQLite scheduler target store."""
        self._db = AsyncDatabaseManager(sqlite_path)

    async def upsert_target(self, target: SchedulerTarget) -> None:
        """Insert or update a target by stable provider/session key."""
        key = _target_key(target)
        async with self._db.transaction() as session:
            existing = await session.scalar(
                select(SchedulerTargetModel.last_scheduler_attempt_at).where(
                    SchedulerTargetModel.provider == key[0],
                    SchedulerTargetModel.provider_subject == key[1],
                    SchedulerTargetModel.provider_space_ref == key[2],
                    SchedulerTargetModel.session_id == key[3],
                )
            )
            last_attempt = (
                str(existing)
                if existing is not None
                else _datetime_to_text(target.last_scheduler_attempt_at)
            )

            stmt = insert(SchedulerTargetModel).values(
                provider=key[0],
                provider_subject=key[1],
                provider_space_ref=key[2],
                session_id=key[3],
                actor_id=_optional_text(target.actor_id),
                account_id=_optional_text(target.account_id),
                space_id=_optional_text(target.space_id),
                display_name=target.display_name,
                last_observed_at=_required_datetime_to_text(target.last_observed_at),
                last_scheduler_attempt_at=last_attempt,
                stale_after=_datetime_to_text(target.stale_after),
                route_display_name=target.route.display_name,
            )

            stmt = stmt.on_conflict_do_update(
                index_elements=["provider", "provider_subject", "provider_space_ref", "session_id"],
                set_={
                    "actor_id": stmt.excluded.actor_id,
                    "account_id": stmt.excluded.account_id,
                    "space_id": stmt.excluded.space_id,
                    "display_name": stmt.excluded.display_name,
                    "last_observed_at": stmt.excluded.last_observed_at,
                    "last_scheduler_attempt_at": last_attempt,
                    "stale_after": stmt.excluded.stale_after,
                    "route_display_name": stmt.excluded.route_display_name,
                },
            )
            await session.execute(stmt)

    async def list_targets(
        self,
        *,
        now: datetime,
    ) -> tuple[SchedulerTarget, ...]:
        """Return non-stale targets in deterministic order."""
        async with self._db.transaction() as session:
            now_text = _datetime_to_text(now)
            result = await session.scalars(
                select(SchedulerTargetModel)
                .where(
                    (SchedulerTargetModel.stale_after.is_(None))
                    | (SchedulerTargetModel.stale_after > now_text)
                )
                .order_by(
                    SchedulerTargetModel.provider,
                    SchedulerTargetModel.provider_subject,
                    SchedulerTargetModel.provider_space_ref,
                    SchedulerTargetModel.session_id,
                )
            )
            return tuple(_model_to_target(row) for row in result.all())

    async def mark_scheduler_attempt(
        self,
        target: SchedulerTarget,
        *,
        attempted_at: datetime,
    ) -> None:
        """Update one target's scheduler attempt timestamp."""
        key = _target_key(target)
        async with self._db.transaction() as session:
            model = await session.scalar(
                select(SchedulerTargetModel).where(
                    SchedulerTargetModel.provider == key[0],
                    SchedulerTargetModel.provider_subject == key[1],
                    SchedulerTargetModel.provider_space_ref == key[2],
                    SchedulerTargetModel.session_id == key[3],
                )
            )
            if model is not None:
                model.last_scheduler_attempt_at = _datetime_to_text(attempted_at)

    async def close(self) -> None:
        """Close the underlying SQLite connection."""
        await self._db.close()


def _model_to_target(model: SchedulerTargetModel) -> SchedulerTarget:
    return SchedulerTarget(
        actor_id=_optional_new_type(ActorId, model.actor_id),
        account_id=_optional_new_type(AccountId, model.account_id),
        space_id=_optional_new_type(SpaceId, model.space_id),
        session_id=SessionId(str(model.session_id)),
        route=DeliveryRouteHint(
            provider=str(model.provider),
            provider_subject=_empty_to_none(model.provider_subject),
            provider_space_ref=_empty_to_none(model.provider_space_ref),
            display_name=model.route_display_name,
        ),
        display_name=model.display_name,
        last_observed_at=_text_to_datetime(str(model.last_observed_at)),
        last_scheduler_attempt_at=_optional_datetime(model.last_scheduler_attempt_at),
        stale_after=_optional_datetime(model.stale_after),
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
