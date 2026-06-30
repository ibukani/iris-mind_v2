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
