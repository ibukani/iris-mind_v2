"""SQLite-backed affect baseline store."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from sqlalchemy import select

from iris.adapters.persistence.sqlite.context import SQLitePersistenceContext
from iris.adapters.persistence.sqlite.engine import AsyncDatabaseManager
from iris.adapters.persistence.sqlite.schema.affect import AffectModel
from iris.contracts.affect import AffectBaselineRecord, AffectScope, AffectStore
from iris.core.datetime_utils import now_utc, parse_datetime
from iris.core.ids import ActorId, ObservationId

if TYPE_CHECKING:
    from pathlib import Path

_GLOBAL_KEY = "__global__"


class SQLiteAffectStore(AffectStore):
    """Global / actor-scoped affect baseline の SQLite store."""

    def __init__(self, db: str | Path | AsyncDatabaseManager | SQLitePersistenceContext) -> None:
        """SQLite DB path を受け取り、manager を初期化する."""
        if hasattr(db, "db"):
            self._manager = db.db  # type: ignore
        elif isinstance(db, AsyncDatabaseManager):
            self._manager = db
        else:
            self._manager = AsyncDatabaseManager(db)  # type: ignore

    async def close(self) -> None:
        """Close the database manager."""
        await self._manager.close()

    @staticmethod
    def _model_to_record(model: AffectModel) -> AffectBaselineRecord:
        actor_id = model.actor_id
        source = model.source_observation_id
        return AffectBaselineRecord(
            scope=_scope_from_str(model.scope),
            actor_id=ActorId(str(actor_id)) if actor_id is not None else None,
            mood_label=model.mood_label,
            valence=model.valence,
            arousal=model.arousal,
            dominance=model.dominance,
            affect_summary=model.affect_summary,
            source_observation_id=ObservationId(str(source)) if source is not None else None,
            created_at=parse_datetime(model.created_at),
            updated_at=parse_datetime(model.updated_at),
            version=model.version,
        )

    @override
    async def get_global(self) -> AffectBaselineRecord | None:
        """Global affect baseline を取得する.

        Returns:
            保存済み global baseline。存在しない場合は None。
        """
        return await self._get(_GLOBAL_KEY)

    @override
    async def upsert_global(self, record: AffectBaselineRecord) -> AffectBaselineRecord:
        """Global affect baseline を保存して返す.

        Returns:
            保存後の AffectBaselineRecord。

        Raises:
            ValueError: record.scope が global ではない場合。
        """
        if record.scope != AffectScope.GLOBAL:
            msg = "upsert_global requires scope='global'"
            raise ValueError(msg)
        return await self._upsert(record, owner_key=_GLOBAL_KEY)

    @override
    async def get_for_actor(self, actor_id: ActorId) -> AffectBaselineRecord | None:
        """Actor-scoped affect baseline を取得する.

        Returns:
            保存済み actor-scoped baseline。存在しない場合は None。
        """
        return await self._get(str(actor_id))

    @override
    async def upsert_for_actor(self, record: AffectBaselineRecord) -> AffectBaselineRecord:
        """Actor-scoped affect baseline を保存して返す.

        Returns:
            保存後の AffectBaselineRecord。

        Raises:
            ValueError: record.scope が actor ではないか actor_id がない場合。
        """
        if record.scope != AffectScope.ACTOR or record.actor_id is None:
            msg = "upsert_for_actor requires scope='actor' and actor_id"
            raise ValueError(msg)
        return await self._upsert(record, owner_key=str(record.actor_id))

    async def _get(self, owner_key: str) -> AffectBaselineRecord | None:
        async with self._manager.transaction() as session:
            stmt = select(AffectModel).where(AffectModel.owner_key == owner_key)
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            if not model:
                return None
            return self._model_to_record(model)

    async def _upsert(
        self,
        record: AffectBaselineRecord,
        *,
        owner_key: str,
    ) -> AffectBaselineRecord:
        now = now_utc()
        current = await self._get(owner_key)
        stored = record.model_copy(update={
            "created_at": current.created_at if current else record.created_at or now,
            "updated_at": now,
        })
        async with self._manager.transaction() as session:
            stmt = select(AffectModel).where(AffectModel.owner_key == owner_key)
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()

            source = stored.source_observation_id
            source_str = str(source) if source is not None else None
            actor_str = str(stored.actor_id) if stored.actor_id is not None else None
            created_str = stored.created_at.isoformat() if stored.created_at else now.isoformat()
            updated_str = stored.updated_at.isoformat() if stored.updated_at else now.isoformat()

            if model:
                model.scope = stored.scope
                model.actor_id = actor_str
                model.mood_label = stored.mood_label
                model.valence = stored.valence
                model.arousal = stored.arousal
                model.dominance = stored.dominance
                model.affect_summary = stored.affect_summary
                model.source_observation_id = source_str
                model.updated_at = updated_str
                model.version = stored.version
            else:
                new_model = AffectModel(
                    owner_key=owner_key,
                    scope=stored.scope,
                    actor_id=actor_str,
                    mood_label=stored.mood_label,
                    valence=stored.valence,
                    arousal=stored.arousal,
                    dominance=stored.dominance,
                    affect_summary=stored.affect_summary,
                    source_observation_id=source_str,
                    created_at=created_str,
                    updated_at=updated_str,
                    version=stored.version,
                )
                session.add(new_model)

        return stored


def _scope_from_str(value: str) -> AffectScope:
    try:
        return AffectScope(value)
    except ValueError as err:
        msg = f"unknown affect scope: {value}"
        raise ValueError(msg) from err
