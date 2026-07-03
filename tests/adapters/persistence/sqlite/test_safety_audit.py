"""SQLite safety audit journal tests。"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta
import sqlite3
from typing import TYPE_CHECKING

import pytest

from iris.adapters.persistence.sqlite.schema.safety_audit import (
    SAFETY_AUDIT_FORBIDDEN_RAW_CONTENT_COLUMNS,
)
from iris.adapters.persistence.sqlite.stores.safety_audit import SQLiteSafetyAuditJournal
from iris.core.ids import ObservationId
from iris.runtime.state.safety_audit import SafetyAuditRecord, SafetyAuditStage
from iris.safety.policy_engine import DeliverySource, SafetyRiskLevel

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.anyio
_NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
_TARGET_KEY = "discord:user-1:space-1"


async def test_sqlite_safety_audit_survives_restart_and_counts_delivery_blocks(
    tmp_path: Path,
) -> None:
    """SQLite backend は restart 後も delivery block count を参照できる。"""
    db_path = tmp_path / "state.sqlite3"
    journal = SQLiteSafetyAuditJournal(db_path)
    await journal.append(
        _record(stage=SafetyAuditStage.DELIVERY, allowed=False, reason="quiet_hours")
    )
    assert await journal.recent_block_count(_TARGET_KEY, since=_NOW - timedelta(minutes=5)) == 1
    await journal.close()

    reopened = SQLiteSafetyAuditJournal(db_path)
    try:
        assert (
            await reopened.recent_block_count(
                _TARGET_KEY,
                since=_NOW - timedelta(minutes=5),
            )
            == 1
        )
    finally:
        await reopened.close()


async def test_sqlite_safety_audit_records_output_and_delivery_stages(tmp_path: Path) -> None:
    """Output block と delivery block は stage を分けて durable に残る。"""
    db_path = tmp_path / "state.sqlite3"
    journal = SQLiteSafetyAuditJournal(db_path)
    await journal.append(
        _record(stage=SafetyAuditStage.OUTPUT, allowed=False, reason="output_block")
    )
    await journal.append(
        _record(stage=SafetyAuditStage.DELIVERY, allowed=False, reason="quiet_hours")
    )
    await journal.close()

    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT
                stage, allowed, reason, risk_level, source, policy,
                policy_version, retention_until
            FROM safety_audit_records
            ORDER BY stage, reason
            """
        ).fetchall()

    assert rows == [
        (
            "delivery",
            0,
            "quiet_hours",
            "medium",
            "proactive_idle_tick",
            "strict_delivery",
            "1",
            "2026-04-01T12:00:00+00:00",
        ),
        (
            "output",
            0,
            "output_block",
            "medium",
            "proactive_idle_tick",
            "strict_delivery",
            "1",
            "2026-04-01T12:00:00+00:00",
        ),
    ]


async def test_sqlite_safety_audit_schema_does_not_store_raw_content(tmp_path: Path) -> None:
    """Audit schema は raw user text / generated output body 用 column を持たない。"""
    raw_user_text = "raw user message that must not be persisted"
    generated_output_body = "generated output body that must not be persisted"
    db_path = tmp_path / "state.sqlite3"
    journal = SQLiteSafetyAuditJournal(db_path)
    await journal.append(
        _record(
            stage=SafetyAuditStage.OUTPUT,
            allowed=False,
            reason="blocked_without_raw_content",
        )
    )
    await journal.close()

    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        column_rows = conn.execute("PRAGMA table_info(safety_audit_records)").fetchall()
        columns = {str(row[1]) for row in column_rows}
        row_values = conn.execute("SELECT * FROM safety_audit_records").fetchone()

    assert columns.isdisjoint(SAFETY_AUDIT_FORBIDDEN_RAW_CONTENT_COLUMNS)
    assert row_values is not None
    serialized_values = tuple(str(value) for value in row_values if value is not None)
    assert raw_user_text not in serialized_values
    assert generated_output_body not in serialized_values


async def test_sqlite_safety_audit_ignores_non_delivery_allowed_and_old_records(
    tmp_path: Path,
) -> None:
    """recent_block_count は同一 target の期間内 delivery block だけを見る。"""
    db_path = tmp_path / "state.sqlite3"
    journal = SQLiteSafetyAuditJournal(db_path)
    records = (
        _record(stage=SafetyAuditStage.OUTPUT, allowed=False, reason="output_block"),
        _record(stage=SafetyAuditStage.DELIVERY, allowed=True, reason="allowed"),
        _record(
            stage=SafetyAuditStage.DELIVERY,
            allowed=False,
            reason="old_block",
            occurred_at=_NOW - timedelta(hours=2),
        ),
        _record(
            stage=SafetyAuditStage.DELIVERY,
            allowed=False,
            reason="other_target",
            target_key="discord:other:space-1",
        ),
    )
    for record in records:
        await journal.append(record)

    assert await journal.recent_block_count(_TARGET_KEY, since=_NOW - timedelta(hours=1)) == 0
    await journal.close()


def test_sqlite_safety_audit_rejects_non_positive_retention_days(tmp_path: Path) -> None:
    """Retention policy MVP は正の保持期間だけを許可する。"""
    with pytest.raises(ValueError, match="retention_days must be at least 1"):
        SQLiteSafetyAuditJournal(tmp_path / "state.sqlite3", retention_days=0)


def _record(
    *,
    stage: SafetyAuditStage,
    allowed: bool,
    reason: str,
    occurred_at: datetime = _NOW,
    target_key: str = _TARGET_KEY,
) -> SafetyAuditRecord:
    return SafetyAuditRecord(
        observation_id=ObservationId(f"obs-{stage.value}-{reason}"),
        occurred_at=occurred_at,
        stage=stage,
        allowed=allowed,
        reason=reason,
        risk_level=SafetyRiskLevel.MEDIUM,
        source=DeliverySource.PROACTIVE_IDLE_TICK,
        target_key=target_key,
        policy="strict_delivery",
        policy_version="1",
    )
