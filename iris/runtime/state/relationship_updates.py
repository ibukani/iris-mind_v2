"""Process-local relationship update candidate store。"""

from __future__ import annotations

from threading import RLock
from typing import TYPE_CHECKING, override

from iris.contracts.relationship_update import (
    RelationshipUpdateCandidateId,
    RelationshipUpdateCandidateRecord,
    RelationshipUpdateCandidateStore,
)

if TYPE_CHECKING:
    from datetime import datetime


class InMemoryRelationshipUpdateCandidateStore(RelationshipUpdateCandidateStore):
    """Durable relationship state の手前で candidate を冪等保持する。"""

    def __init__(self) -> None:
        """空の process-local store を作る。"""
        self._records: dict[RelationshipUpdateCandidateId, RelationshipUpdateCandidateRecord] = {}
        self._idempotency_keys: dict[str, RelationshipUpdateCandidateId] = {}
        self._lock = RLock()

    @override
    def add_nowait(
        self,
        record: RelationshipUpdateCandidateRecord,
    ) -> RelationshipUpdateCandidateRecord:
        """Candidate を idempotency key 付きで追加する。

        Returns:
            新規または既存の candidate record。
        """
        with self._lock:
            existing_record = self._records.get(record.candidate_id)
            if existing_record is not None:
                return existing_record
            existing_id = self._idempotency_keys.get(record.idempotency_key)
            if existing_id is not None:
                return self._records[existing_id]
            self._records[record.candidate_id] = record
            self._idempotency_keys[record.idempotency_key] = record.candidate_id
            return record

    def list_records(self) -> tuple[RelationshipUpdateCandidateRecord, ...]:
        """Candidate を作成時刻と ID の決定的順序で返す。

        Returns:
            作成時刻と candidate ID で整列済みの records。
        """
        with self._lock:
            records = sorted(
                self._records.values(),
                key=_record_sort_key,
            )
            return tuple(records)


def _record_sort_key(record: RelationshipUpdateCandidateRecord) -> tuple[datetime, str]:
    return record.created_at, str(record.candidate_id)
