"""SQLite-backed durable MemoryCandidateReviewStore implementation。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, override

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from iris.adapters.persistence.sqlite.serialization import (
    datetime_to_text,
    optional_datetime,
    optional_new_type,
    optional_text,
    required_datetime_to_text,
    text_to_datetime,
)
from iris.adapters.persistence.sqlite.stores._managed_database import ManagedSQLiteStore
from iris.contracts.memory import MemoryKind
from iris.contracts.memory_candidates import (
    MemoryCandidate,
    MemoryCandidateSensitivity,
    MemoryCandidateSource,
    MemoryRetentionPolicy,
)
from iris.contracts.review_candidates import (
    ReviewCandidateFilter,
    ReviewCandidateStatus,
    ReviewCandidateType,
)
from iris.core.ids import AccountId, ActorId, ObservationId, SpaceId
from iris.core.metadata import immutable_metadata
from iris.runtime.state.memory_candidates import (
    MemoryCandidateReviewId,
    MemoryCandidateReviewRecord,
    MemoryCandidateReviewStatus,
    MemoryCandidateReviewStore,
    MemoryCandidateReviewUpdate,
)

if TYPE_CHECKING:
    from datetime import datetime
    import sqlite3


type _SqlParams = tuple[object, ...]


@dataclass(frozen=True)
class _ListQuery:
    """review candidate list SQL と bind 値。"""

    sql: str
    params: _SqlParams


class _MemoryCandidatePayload(BaseModel):
    """JSON payload for durable memory candidate storage。"""

    model_config = ConfigDict(frozen=True)

    text: str
    kind: str
    salience: float
    confidence: float
    source: str
    reason: str | None = None
    retention_policy: str
    sensitivity: str
    review_required: bool
    actor_id: str | None = None
    space_id: str | None = None
    source_observation_id: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


_METADATA_ADAPTER = TypeAdapter(dict[str, str])


class SQLiteMemoryCandidateReviewStore(ManagedSQLiteStore, MemoryCandidateReviewStore):
    """SQLite-backed durable review store for implicit memory candidates。

    ``add_nowait`` は同期 worker から呼ばれるため同期 transaction のまま実装する。
    async API は同じ同期処理を ``asyncio.to_thread`` へ逃がす。
    """

    @override
    async def add(self, record: MemoryCandidateReviewRecord) -> MemoryCandidateReviewRecord:
        """候補を冪等に追加する。

        Returns:
            新規または既存の review record。
        """
        return await asyncio.to_thread(self.add_nowait, record)

    @override
    def add_nowait(self, record: MemoryCandidateReviewRecord) -> MemoryCandidateReviewRecord:
        """同期 worker から候補を冪等に追加する。

        Returns:
            新規または既存の review record。
        """
        with self._db.transaction(immediate=True) as conn:
            existing = _find_existing(conn, record)
            if existing is not None:
                return existing
            conn.execute(
                """
                INSERT INTO memory_candidate_reviews (
                    candidate_id, idempotency_key, status, candidate_type, candidate_json,
                    candidate_text, candidate_kind, candidate_source, candidate_reason,
                    candidate_confidence, candidate_salience,
                    candidate_retention_policy, candidate_sensitivity,
                    candidate_review_required, actor_id, account_id, space_id,
                    source_observation_id, reviewed_at, reviewed_by, review_reason,
                    promoted_memory_id, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _record_to_row(record),
            )
            return record

    @override
    async def get(
        self,
        candidate_id: MemoryCandidateReviewId,
    ) -> MemoryCandidateReviewRecord | None:
        """ID に一致する review candidate を返す。

        Returns:
            Matching record。存在しない場合は None。
        """
        return await asyncio.to_thread(self._get_sync, candidate_id)

    @override
    async def list_pending(
        self,
        *,
        actor_id: ActorId | None = None,
        account_id: AccountId | None = None,
        space_id: SpaceId | None = None,
        limit: int = 50,
    ) -> tuple[MemoryCandidateReviewRecord, ...]:
        """Review 待ち candidate を決定的順序で返す。

        Returns:
            Pending review candidate の一覧。
        """
        return await self.list_by_status(
            MemoryCandidateReviewStatus.PENDING_REVIEW,
            actor_id=actor_id,
            account_id=account_id,
            space_id=space_id,
            limit=limit,
        )

    @override
    async def list_by_status(
        self,
        status: MemoryCandidateReviewStatus,
        *,
        actor_id: ActorId | None = None,
        account_id: AccountId | None = None,
        space_id: SpaceId | None = None,
        limit: int = 50,
    ) -> tuple[MemoryCandidateReviewRecord, ...]:
        """指定 status の review candidate を決定的順序で返す。

        Returns:
            作成時刻と candidate id で整列済みの matching record。
        """
        return await self.list_by_filter(
            ReviewCandidateFilter.model_construct(
                status=ReviewCandidateStatus(status.value),
                candidate_type=None,
                actor_id=actor_id,
                account_id=account_id,
                space_id=space_id,
                limit=limit,
            )
        )

    @override
    async def list_by_filter(
        self,
        query: ReviewCandidateFilter,
    ) -> tuple[MemoryCandidateReviewRecord, ...]:
        """Review service boundary 用 filter で candidate を返す。

        Returns:
            作成時刻と candidate id で整列済みの matching record。
        """
        return await asyncio.to_thread(self._list_by_filter_sync, query)

    @override
    async def update_status(
        self,
        candidate_id: MemoryCandidateReviewId,
        status: MemoryCandidateReviewStatus,
        *,
        updated_at: datetime,
    ) -> MemoryCandidateReviewRecord | None:
        """Review status を更新する。

        Returns:
            更新後 record。存在しない場合は None。
        """
        return await self.update_review(
            candidate_id,
            MemoryCandidateReviewUpdate(status=status, updated_at=updated_at),
        )

    @override
    async def update_review(
        self,
        candidate_id: MemoryCandidateReviewId,
        update: MemoryCandidateReviewUpdate,
    ) -> MemoryCandidateReviewRecord | None:
        """Review lifecycle と review/promotion metadata を更新する。

        Returns:
            更新後 record。存在しない場合は None。
        """
        return await asyncio.to_thread(self._update_review_sync, candidate_id, update)

    def _get_sync(
        self,
        candidate_id: MemoryCandidateReviewId,
    ) -> MemoryCandidateReviewRecord | None:
        with self._db.transaction() as conn:
            return _get(conn, candidate_id)

    def _list_by_filter_sync(
        self,
        query: ReviewCandidateFilter,
    ) -> tuple[MemoryCandidateReviewRecord, ...]:
        _validate_positive_limit(query.limit)
        list_query = _list_query(query)
        with self._db.transaction() as conn:
            rows = conn.execute(list_query.sql, list_query.params).fetchall()
            return tuple(_row_to_record(row) for row in rows)

    def _update_review_sync(
        self,
        candidate_id: MemoryCandidateReviewId,
        update: MemoryCandidateReviewUpdate,
    ) -> MemoryCandidateReviewRecord | None:
        with self._db.transaction(immediate=True) as conn:
            record = _get(conn, candidate_id)
            if record is None:
                return None
            updated = _apply_update(record, update)
            conn.execute(
                """
                UPDATE memory_candidate_reviews
                SET status = ?, reviewed_at = ?, reviewed_by = ?, review_reason = ?,
                    promoted_memory_id = ?, updated_at = ?
                WHERE candidate_id = ?
                """,
                _update_row(updated),
            )
            return updated


def _find_existing(
    conn: sqlite3.Connection,
    record: MemoryCandidateReviewRecord,
) -> MemoryCandidateReviewRecord | None:
    row = conn.execute(
        """
        SELECT *
        FROM memory_candidate_reviews
        WHERE candidate_id = ? OR idempotency_key = ?
        ORDER BY CASE WHEN candidate_id = ? THEN 0 ELSE 1 END
        LIMIT 1
        """,
        (str(record.candidate_id), record.idempotency_key, str(record.candidate_id)),
    ).fetchone()
    if row is None:
        return None
    return _row_to_record(row)


def _get(
    conn: sqlite3.Connection,
    candidate_id: MemoryCandidateReviewId,
) -> MemoryCandidateReviewRecord | None:
    row = conn.execute(
        "SELECT * FROM memory_candidate_reviews WHERE candidate_id = ?",
        (str(candidate_id),),
    ).fetchone()
    if row is None:
        return None
    return _row_to_record(row)


def _list_query(query: ReviewCandidateFilter) -> _ListQuery:
    status = query.status.value if query.status is not None else None
    candidate_type = query.candidate_type.value if query.candidate_type is not None else None
    return _ListQuery(
        sql=(
            """
            SELECT *
            FROM memory_candidate_reviews
            WHERE (? IS NULL OR status = ?)
            AND (? IS NULL OR candidate_type = ?)
            AND (? IS NULL OR actor_id = ?)
            AND (? IS NULL OR account_id = ?)
            AND (? IS NULL OR space_id = ?)
            ORDER BY created_at, candidate_id
            LIMIT ?
            """
        ),
        params=(
            status,
            status,
            candidate_type,
            candidate_type,
            optional_text(query.actor_id),
            optional_text(query.actor_id),
            optional_text(query.account_id),
            optional_text(query.account_id),
            optional_text(query.space_id),
            optional_text(query.space_id),
            query.limit,
        ),
    )


def _apply_update(
    record: MemoryCandidateReviewRecord,
    update: MemoryCandidateReviewUpdate,
) -> MemoryCandidateReviewRecord:
    return replace(
        record,
        status=update.status,
        updated_at=update.updated_at,
        reviewed_at=update.reviewed_at if update.reviewed_at is not None else record.reviewed_at,
        reviewed_by=update.reviewed_by if update.reviewed_by is not None else record.reviewed_by,
        review_reason=(
            update.review_reason if update.review_reason is not None else record.review_reason
        ),
        promoted_memory_id=(
            update.promoted_memory_id
            if update.promoted_memory_id is not None
            else record.promoted_memory_id
        ),
    )


def _record_to_row(record: MemoryCandidateReviewRecord) -> _SqlParams:
    candidate = record.candidate
    return (
        str(record.candidate_id),
        record.idempotency_key,
        record.status.value,
        record.candidate_type.value,
        _candidate_to_json(candidate),
        candidate.text,
        candidate.kind.value,
        candidate.source.value,
        candidate.reason,
        candidate.confidence,
        candidate.salience,
        candidate.retention_policy.value,
        candidate.sensitivity.value,
        1 if candidate.review_required else 0,
        optional_text(record.actor_id),
        optional_text(record.account_id),
        optional_text(record.space_id),
        optional_text(record.source_observation_id),
        datetime_to_text(record.reviewed_at),
        record.reviewed_by,
        record.review_reason,
        record.promoted_memory_id,
        _mapping_to_json(record.metadata),
        required_datetime_to_text(record.created_at),
        required_datetime_to_text(record.updated_at),
    )


def _update_row(record: MemoryCandidateReviewRecord) -> _SqlParams:
    return (
        record.status.value,
        datetime_to_text(record.reviewed_at),
        record.reviewed_by,
        record.review_reason,
        record.promoted_memory_id,
        required_datetime_to_text(record.updated_at),
        str(record.candidate_id),
    )


def _row_to_record(row: sqlite3.Row) -> MemoryCandidateReviewRecord:
    return MemoryCandidateReviewRecord(
        candidate_id=MemoryCandidateReviewId(row["candidate_id"]),
        candidate=_candidate_from_json(row["candidate_json"]),
        created_at=text_to_datetime(row["created_at"]),
        updated_at=text_to_datetime(row["updated_at"]),
        idempotency_key=row["idempotency_key"],
        status=MemoryCandidateReviewStatus(row["status"]),
        candidate_type=ReviewCandidateType(row["candidate_type"]),
        actor_id=optional_new_type(ActorId, row["actor_id"]),
        account_id=optional_new_type(AccountId, row["account_id"]),
        space_id=optional_new_type(SpaceId, row["space_id"]),
        source_observation_id=optional_new_type(ObservationId, row["source_observation_id"]),
        reviewed_at=optional_datetime(row["reviewed_at"]),
        reviewed_by=row["reviewed_by"],
        review_reason=row["review_reason"],
        promoted_memory_id=row["promoted_memory_id"],
        metadata=immutable_metadata(_json_mapping(row["metadata_json"])),
    )


def _candidate_to_json(candidate: MemoryCandidate) -> str:
    return _MemoryCandidatePayload(
        text=candidate.text,
        kind=candidate.kind.value,
        salience=candidate.salience,
        confidence=candidate.confidence,
        source=candidate.source.value,
        reason=candidate.reason,
        retention_policy=candidate.retention_policy.value,
        sensitivity=candidate.sensitivity.value,
        review_required=candidate.review_required,
        actor_id=optional_text(candidate.actor_id),
        space_id=optional_text(candidate.space_id),
        source_observation_id=optional_text(candidate.source_observation_id),
        metadata=dict(candidate.metadata),
    ).model_dump_json()


def _candidate_from_json(payload_json: str) -> MemoryCandidate:
    payload = _MemoryCandidatePayload.model_validate_json(payload_json)
    return MemoryCandidate(
        text=payload.text,
        kind=MemoryKind(payload.kind),
        salience=payload.salience,
        confidence=payload.confidence,
        source=MemoryCandidateSource(payload.source),
        reason=payload.reason,
        retention_policy=MemoryRetentionPolicy(payload.retention_policy),
        sensitivity=MemoryCandidateSensitivity(payload.sensitivity),
        review_required=payload.review_required,
        actor_id=optional_new_type(ActorId, payload.actor_id),
        space_id=optional_new_type(SpaceId, payload.space_id),
        source_observation_id=optional_new_type(ObservationId, payload.source_observation_id),
        metadata=immutable_metadata(payload.metadata),
    )


def _mapping_to_json(mapping: object) -> str:
    return _METADATA_ADAPTER.dump_json(_METADATA_ADAPTER.validate_python(mapping)).decode("utf-8")


def _json_mapping(value: object | None) -> dict[str, str]:
    if value is None:
        return {}
    return dict(_METADATA_ADAPTER.validate_json(str(value)))


def _validate_positive_limit(limit: int) -> None:
    if limit < 1:
        message = "memory candidate review list limit must be >= 1"
        raise ValueError(message)
