"""Runtime safety audit journal tests。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from iris.core.ids import ObservationId
from iris.runtime.state.safety_audit import (
    InMemorySafetyAuditJournal,
    SafetyAuditRecord,
    SafetyAuditStage,
)
from iris.safety.policy_engine import DeliverySource, SafetyRiskLevel

pytestmark = pytest.mark.anyio


async def test_audit_counts_recent_blocks_without_raw_content() -> None:
    """Audit は typed metadata のみ保持し recent block を数える。"""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    journal = InMemorySafetyAuditJournal()
    await journal.append(
        SafetyAuditRecord(
            observation_id=ObservationId("obs-1"),
            occurred_at=now,
            stage=SafetyAuditStage.DELIVERY,
            allowed=False,
            reason="quiet_hours",
            risk_level=SafetyRiskLevel.MEDIUM,
            source=DeliverySource.PROACTIVE_IDLE_TICK,
            target_key="target",
            policy="strict_delivery",
            policy_version="1",
        )
    )
    count = await journal.recent_block_count("target", since=now - timedelta(minutes=1))
    assert count == 1
    record = journal.records()[0]
    assert not hasattr(record, "text")
    assert not hasattr(record, "output")


def test_audit_rejects_non_positive_capacity() -> None:
    """Bounded journalは1件未満のcapacityを拒否する。"""
    with pytest.raises(ValueError, match="max_records must be at least 1"):
        InMemorySafetyAuditJournal(max_records=0)


async def test_recent_block_count_ignores_other_targets_stages_allowed_and_old_records() -> None:
    """Recent countは同一targetの期間内delivery blockだけを数える。"""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    journal = InMemorySafetyAuditJournal()
    records = (
        _record(now=now, target_key="other", stage=SafetyAuditStage.DELIVERY, allowed=False),
        _record(now=now, target_key="target", stage=SafetyAuditStage.OUTPUT, allowed=False),
        _record(now=now, target_key="target", stage=SafetyAuditStage.DELIVERY, allowed=True),
        _record(
            now=now - timedelta(hours=2),
            target_key="target",
            stage=SafetyAuditStage.DELIVERY,
            allowed=False,
        ),
    )
    for record in records:
        await journal.append(record)

    count = await journal.recent_block_count("target", since=now - timedelta(hours=1))

    assert count == 0


def _record(
    *,
    now: datetime,
    target_key: str,
    stage: SafetyAuditStage,
    allowed: bool,
) -> SafetyAuditRecord:
    return SafetyAuditRecord(
        observation_id=ObservationId(f"obs-{target_key}-{stage}-{allowed}"),
        occurred_at=now,
        stage=stage,
        allowed=allowed,
        reason="test",
        risk_level=SafetyRiskLevel.MEDIUM,
        source=DeliverySource.PROACTIVE_IDLE_TICK,
        target_key=target_key,
        policy="strict_delivery",
        policy_version="1",
    )


async def test_in_memory_audit_is_process_local_across_restart_equivalent() -> None:
    """In-memory backend は restart 相当の再生成で block history を失う。"""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    journal = InMemorySafetyAuditJournal()
    await journal.append(
        _record(
            now=now,
            target_key="target",
            stage=SafetyAuditStage.DELIVERY,
            allowed=False,
        )
    )
    assert await journal.recent_block_count("target", since=now - timedelta(minutes=1)) == 1

    restarted = InMemorySafetyAuditJournal()

    assert await restarted.recent_block_count("target", since=now - timedelta(minutes=1)) == 0
