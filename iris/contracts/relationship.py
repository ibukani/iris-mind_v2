"""関係性状態の永続化契約。"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, model_validator

from iris.core.ids import ActorId, ObservationId


def _validate_range(value: float, *, minimum: float, maximum: float, field_name: str) -> None:
    """数値が指定範囲に収まることを検証する。

    Raises:
        ValueError: 値が指定範囲外の場合。
    """
    if not minimum <= value <= maximum:
        msg = f"{field_name} must be between {minimum} and {maximum}: {value}"
        raise ValueError(msg)


class RelationshipSnapshotRecord(BaseModel):
    """ActorId を主キーに持つ現在の関係性スナップショット。"""

    model_config = ConfigDict(frozen=True)

    actor_id: ActorId
    actor_label: str | None = None
    affinity: float = 0.0
    trust: float = 0.5
    familiarity: float = 0.0
    relationship_summary: str | None = None
    source_observation_id: ObservationId | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    version: int = 1

    @model_validator(mode="after")
    def _validate_record(self) -> RelationshipSnapshotRecord:
        """永続化境界で扱える関係性値だけを許可する。"""
        if not self.actor_id:
            msg = "actor_id is required for durable relationship records"
            raise ValueError(msg)
        _validate_range(self.affinity, minimum=-1.0, maximum=1.0, field_name="affinity")
        _validate_range(self.trust, minimum=0.0, maximum=1.0, field_name="trust")
        _validate_range(
            self.familiarity,
            minimum=0.0,
            maximum=1.0,
            field_name="familiarity",
        )
        if self.version < 1:
            msg = "version must be greater than or equal to 1"
            raise ValueError(msg)
        return self


class RelationshipStore(Protocol):
    """ActorId ごとの現在の関係性スナップショットを保存するストア。"""

    async def get(self, actor_id: ActorId) -> RelationshipSnapshotRecord | None:
        """ActorId に対応する関係性スナップショットを取得する。"""
        ...

    async def upsert(
        self,
        record: RelationshipSnapshotRecord,
    ) -> RelationshipSnapshotRecord:
        """関係性スナップショットを作成または更新して保存後の値を返す。"""
        ...
