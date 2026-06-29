"""SQLite-backed affect baseline store."""

from __future__ import annotations

from typing import override

from sqlalchemy import select

from iris.adapters.persistence.sqlite.context import (
    SQLiteDatabaseInput,
    resolve_database_manager,
)
from iris.adapters.persistence.sqlite.schema.affect import AffectModel
from iris.adapters.persistence.sqlite.serialization import (
    optional_new_type,
    optional_text,
    required_datetime_to_text,
)
from iris.contracts.affect import AffectBaselineRecord, AffectScope, AffectStore
from iris.core.datetime_utils import now_utc, parse_datetime
from iris.core.ids import ActorId, ObservationId

_GLOBAL_KEY = "__global__"


class SQLiteAffectStore(AffectStore):
    """Global / actor-scoped affect baseline の SQLite store."""

    def __init__(self, db: SQLiteDatabaseInput) -> None:
        """SQLite DB path を受け取り、manager を初期化する."""
        self._manager = resolve_database_manager(db)

    async def close(self) -> None:
        """Close the database manager."""
        await self._manager.close()

    @staticmethod
    def _model_to_record(model: AffectModel) -> AffectBaselineRecord:
        return AffectBaselineRecord(
            scope=_scope_from_str(model.scope),
            actor_id=optional_new_type(ActorId, model.actor_id),
            mood_label=model.mood_label,
            valence=model.valence,
            arousal=model.arousal,
            dominance=model.dominance,
            affect_summary=model.affect_summary,
            source_observation_id=optional_new_type(
                ObservationId,
                model.source_observation_id,
            ),
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
            model = await session.scalar(stmt)
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
        stored = record.model_copy(
            update={
                "created_at": current.created_at if current else record.created_at or now,
                "updated_at": now,
            }
        )
        async with self._manager.transaction() as session:
            stmt = select(AffectModel).where(AffectModel.owner_key == owner_key)
            model = await session.scalar(stmt)

            source_str = optional_text(stored.source_observation_id)
            actor_str = optional_text(stored.actor_id)
            created_str = required_datetime_to_text(stored.created_at or now)
            updated_str = required_datetime_to_text(stored.updated_at or now)

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
