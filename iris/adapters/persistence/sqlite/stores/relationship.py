"""SQLite-backed relationship state store."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from sqlalchemy import select

from iris.adapters.persistence.sqlite.context import SQLitePersistenceContext
from iris.adapters.persistence.sqlite.engine import AsyncDatabaseManager
from iris.adapters.persistence.sqlite.schema.relationship import RelationshipModel
from iris.contracts.relationship import RelationshipSnapshotRecord, RelationshipStore
from iris.core.datetime_utils import now_utc, parse_datetime
from iris.core.ids import ActorId, ObservationId

if TYPE_CHECKING:
    from pathlib import Path


class SQLiteRelationshipStore(RelationshipStore):
    """ActorId を主キーにした SQLite relationship state store."""

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
    def _model_to_record(model: RelationshipModel) -> RelationshipSnapshotRecord:
        """Convert a RelationshipModel to a RelationshipSnapshotRecord.

        Returns:
            RelationshipSnapshotRecord: The resulting record.
        """
        source = model.source_observation_id
        return RelationshipSnapshotRecord(
            actor_id=ActorId(model.actor_id),
            actor_label=model.actor_label,
            affinity=model.affinity,
            trust=model.trust,
            familiarity=model.familiarity,
            relationship_summary=model.relationship_summary,
            source_observation_id=ObservationId(source) if source is not None else None,
            created_at=parse_datetime(model.created_at),
            updated_at=parse_datetime(model.updated_at),
            version=model.version,
        )

    @override
    async def get(self, actor_id: ActorId) -> RelationshipSnapshotRecord | None:
        """ActorId に対応する relationship state を取得する.

        Returns:
            保存済み record。存在しない場合は None。
        """
        async with self._manager.transaction() as session:
            stmt = select(RelationshipModel).where(RelationshipModel.actor_id == str(actor_id))
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            if not model:
                return None
            return self._model_to_record(model)

    @override
    async def upsert(
        self,
        record: RelationshipSnapshotRecord,
    ) -> RelationshipSnapshotRecord:
        """Relationship state を upsert して保存後の record を返す.

        Returns:
            保存後の RelationshipSnapshotRecord。
        """
        now = now_utc()
        current = await self.get(record.actor_id)
        stored = record.model_copy(update={
            "created_at": current.created_at if current else record.created_at or now,
            "updated_at": now,
        })
        async with self._manager.transaction() as session:
            stmt = select(RelationshipModel).where(
                RelationshipModel.actor_id == str(stored.actor_id)
            )
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()

            source = stored.source_observation_id
            source_str = str(source) if source is not None else None
            created_str = stored.created_at.isoformat() if stored.created_at else now.isoformat()
            updated_str = stored.updated_at.isoformat() if stored.updated_at else now.isoformat()

            if model:
                model.actor_label = stored.actor_label
                model.affinity = stored.affinity
                model.trust = stored.trust
                model.familiarity = stored.familiarity
                model.relationship_summary = stored.relationship_summary
                model.source_observation_id = source_str
                model.updated_at = updated_str
                model.version = stored.version
            else:
                new_model = RelationshipModel(
                    actor_id=str(stored.actor_id),
                    actor_label=stored.actor_label,
                    affinity=stored.affinity,
                    trust=stored.trust,
                    familiarity=stored.familiarity,
                    relationship_summary=stored.relationship_summary,
                    source_observation_id=source_str,
                    created_at=created_str,
                    updated_at=updated_str,
                    version=stored.version,
                )
                session.add(new_model)

        return stored
