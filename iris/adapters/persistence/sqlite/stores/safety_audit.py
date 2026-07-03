"""SQLite-backed durable SafetyAuditJournal implementation。"""

from __future__ import annotations

from datetime import timedelta
import hashlib
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert

from iris.adapters.persistence.sqlite.context import (
    SQLiteDatabaseInput,
    resolve_database_manager,
)
from iris.adapters.persistence.sqlite.schema.safety_audit import SafetyAuditRecordModel
from iris.adapters.persistence.sqlite.serialization import (
    datetime_to_text,
    required_datetime_to_text,
)
from iris.runtime.state.safety_audit import SafetyAuditRecord, SafetyAuditStage

if TYPE_CHECKING:
    from datetime import datetime

DEFAULT_SAFETY_AUDIT_RETENTION_DAYS = 90


class SQLiteSafetyAuditJournal:
    """SQLite-backed durable safety audit journal。

    Raw user text / generated output body は保存せず、policy decision metadata だけを
    append-only に保持する。retention_until は MVP の削除境界 metadata であり、
    実削除 job は後続 issue で扱う。
    """

    def __init__(
        self,
        db: SQLiteDatabaseInput,
        *,
        retention_days: int = DEFAULT_SAFETY_AUDIT_RETENTION_DAYS,
    ) -> None:
        """SQLite safety audit journal を作成する。

        Args:
            db: SQLite database manager / context / path。
            retention_days: retention_until を決める日数。

        Raises:
            ValueError: retention_days が1未満の場合。
        """
        if retention_days < 1:
            message = "retention_days must be at least 1"
            raise ValueError(message)
        self._db = resolve_database_manager(db)
        self._retention_days = retention_days

    async def append(self, record: SafetyAuditRecord) -> None:
        """Safety audit record を append-only table に保存する。"""
        values = _record_to_values(record, retention_days=self._retention_days)
        stmt = insert(SafetyAuditRecordModel).values(**values)
        stmt = stmt.on_conflict_do_nothing(index_elements=["audit_id"])
        async with self._db.transaction() as session:
            await session.execute(stmt)

    async def recent_block_count(self, target_key: str, *, since: datetime) -> int:
        """同一 target の期間内 delivery block 件数を返す。

        Returns:
            期間内の delivery block 件数。
        """
        since_text = required_datetime_to_text(since)
        async with self._db.transaction() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(SafetyAuditRecordModel)
                .where(
                    SafetyAuditRecordModel.target_key == target_key,
                    SafetyAuditRecordModel.stage == SafetyAuditStage.DELIVERY.value,
                    SafetyAuditRecordModel.allowed == 0,
                    SafetyAuditRecordModel.occurred_at >= since_text,
                )
            )
        return int(count or 0)

    async def close(self) -> None:
        """Underlying SQLite engine を閉じる。"""
        await self._db.close()


def _record_to_values(
    record: SafetyAuditRecord,
    *,
    retention_days: int,
) -> dict[str, str | int | None]:
    retention_until = record.retention_until or record.occurred_at + timedelta(days=retention_days)
    return {
        "audit_id": _audit_id(record),
        "observation_id": str(record.observation_id),
        "occurred_at": required_datetime_to_text(record.occurred_at),
        "stage": record.stage.value,
        "allowed": int(record.allowed),
        "reason": record.reason,
        "risk_level": str(record.risk_level),
        "source": str(record.source),
        "target_key": record.target_key,
        "policy": record.policy,
        "policy_version": record.policy_version,
        "retention_until": datetime_to_text(retention_until),
    }


def _audit_id(record: SafetyAuditRecord) -> str:
    payload = "\0".join(
        (
            str(record.observation_id),
            record.stage.value,
            required_datetime_to_text(record.occurred_at),
            str(record.allowed),
            record.reason,
            str(record.risk_level),
            str(record.source),
            record.target_key,
            record.policy,
            record.policy_version,
        )
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"safety:{digest}"
