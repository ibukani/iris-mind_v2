"""関係性 state のインメモリストア。"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, override

from iris.contracts.relationship import RelationshipSnapshotRecord, RelationshipStore
from iris.core.datetime_utils import now_utc

if TYPE_CHECKING:
    from iris.core.ids import ActorId


class InMemoryRelationshipStore(RelationshipStore):
    """ActorId をキーにした関係性 state のプロセス内ストア。"""

    def __init__(self) -> None:
        """空の関係性ストアを初期化する。"""
        self._records: dict[ActorId, RelationshipSnapshotRecord] = {}

    @override
    def get(self, actor_id: ActorId) -> RelationshipSnapshotRecord | None:
        """ActorId に対応する関係性 state を返す。

        Returns:
            保存済み record。存在しない場合は None。
        """
        return self._records.get(actor_id)

    @override
    def upsert(
        self,
        record: RelationshipSnapshotRecord,
    ) -> RelationshipSnapshotRecord:
        """関係性 state を保存し、保存後の時刻付き record を返す。

        Returns:
            保存後の RelationshipSnapshotRecord。
        """
        now = now_utc()
        current = self._records.get(record.actor_id)
        stored = replace(
            record,
            created_at=current.created_at if current else record.created_at or now,
            updated_at=now,
        )
        self._records[record.actor_id] = stored
        return stored
