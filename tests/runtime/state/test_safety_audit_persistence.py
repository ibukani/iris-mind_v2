"""Runtime wiring level safety audit persistence tests。"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
import sqlite3
from typing import TYPE_CHECKING

import pytest

from iris.contracts.actions import PresentedOutput
from iris.contracts.delivery import DeliveryTarget
from iris.contracts.observations import IdleTickObservation, ObservationContext, ObservationKind
from iris.core.ids import ExternalRef, ObservationId, SessionId
from iris.runtime.config import default_runtime_config
from iris.runtime.config.state import RuntimeStateBackend, RuntimeStateConfig
from iris.runtime.delivery.in_memory import InMemoryDeliveryOutbox
from iris.runtime.scheduler.models import ScheduledObservation
from iris.runtime.scheduler.runner import SchedulerRunner
from iris.runtime.service import ObservationEnvelope, RuntimeResponse
from iris.runtime.state.safety_audit import SafetyAuditRecord, SafetyAuditStage
from iris.runtime.wiring.state import wire_runtime_state
from iris.safety.delivery_gate import StrictDeliverySafetyGate
from iris.safety.policy_engine import DeliverySource, SafetyRiskLevel

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.anyio
_NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
_TARGET_KEY = "discord:user-1:"


@dataclass
class _Runtime:
    output: PresentedOutput

    async def handle_observation(self, envelope: ObservationEnvelope) -> RuntimeResponse:
        return RuntimeResponse(output=self.output, correlation_id=envelope.correlation_id)


class _Scheduler:
    def __init__(self, observation_id: str = "obs-restart") -> None:
        self._observation_id = observation_id

    async def due_observations(self, now: datetime) -> tuple[ScheduledObservation, ...]:
        return (
            ScheduledObservation(
                observation=IdleTickObservation(
                    observation_id=ObservationId(self._observation_id),
                    session_id=SessionId("session-1"),
                    context=ObservationContext(),
                    occurred_at=now,
                    kind=ObservationKind.IDLE_TICK,
                    reason="test",
                    idle_seconds=1000.0,
                ),
                correlation_id=None,
                reason="test",
                target=DeliveryTarget(
                    provider="discord",
                    provider_subject=ExternalRef("user-1"),
                    provider_space_ref=None,
                    session_id=SessionId("session-1"),
                ),
            ),
        )

    async def mark_dispatched(
        self,
        observation_id: ObservationId,
        *,
        dispatched_at: datetime,
    ) -> None:
        _ = observation_id, dispatched_at

    async def mark_failed(
        self,
        observation_id: ObservationId,
        *,
        failed_at: datetime,
        reason: str,
    ) -> None:
        _ = observation_id, failed_at, reason


async def test_sqlite_runtime_wiring_safety_audit_survives_restart(tmp_path: Path) -> None:
    """wire_runtime_state の SQLite safety audit は restart 後も残る。"""
    db_path = tmp_path / "state.sqlite3"
    config = replace(
        default_runtime_config(),
        state=RuntimeStateConfig(backend=RuntimeStateBackend.SQLITE, sqlite_path=str(db_path)),
    )
    stores = wire_runtime_state(config)
    await stores.safety_audit_journal.append(_blocked_record("previous-1"))
    await stores.close()

    restarted = wire_runtime_state(config)
    try:
        count = await restarted.safety_audit_journal.recent_block_count(
            _TARGET_KEY,
            since=_NOW - timedelta(minutes=5),
        )
    finally:
        await restarted.close()

    assert count == 1


async def test_scheduler_uses_durable_recent_block_history_after_restart(tmp_path: Path) -> None:
    """SchedulerRunner は restart 後の durable block history で repeated block を判定する。"""
    db_path = tmp_path / "state.sqlite3"
    config = replace(
        default_runtime_config(),
        state=RuntimeStateConfig(backend=RuntimeStateBackend.SQLITE, sqlite_path=str(db_path)),
    )
    first = wire_runtime_state(config)
    await first.safety_audit_journal.append(_blocked_record("previous-1"))
    await first.safety_audit_journal.append(_blocked_record("previous-2"))
    await first.close()

    restarted = wire_runtime_state(config)
    try:
        runner = SchedulerRunner(
            scheduler=_Scheduler(),
            runtime_service=_Runtime(PresentedOutput(text="generated output")),
            delivery_gate=StrictDeliverySafetyGate(),
            outbox=InMemoryDeliveryOutbox(),
            safety_audit_journal=restarted.safety_audit_journal,
        )
        result = await runner.run_once(_NOW)
    finally:
        await restarted.close()

    assert result.results[0].status == "blocked"
    assert result.results[0].reason == "repeated_recent_blocks"


async def test_scheduler_persists_output_and_delivery_blocks_to_sqlite(tmp_path: Path) -> None:
    """SchedulerRunner が記録した output/delivery block は SQLite restart 後も参照できる。"""
    db_path = tmp_path / "state.sqlite3"
    config = replace(
        default_runtime_config(),
        state=RuntimeStateConfig(backend=RuntimeStateBackend.SQLITE, sqlite_path=str(db_path)),
    )
    first = wire_runtime_state(config)
    output_runner = SchedulerRunner(
        scheduler=_Scheduler("obs-output"),
        runtime_service=_Runtime(PresentedOutput(text=None, safety_block_reason="output_block")),
        delivery_gate=StrictDeliverySafetyGate(),
        outbox=InMemoryDeliveryOutbox(),
        safety_audit_journal=first.safety_audit_journal,
    )
    delivery_runner = SchedulerRunner(
        scheduler=_Scheduler("obs-delivery"),
        runtime_service=_Runtime(
            PresentedOutput(
                text="generated output",
                policy_constraint_names=("sensitive_safety_context",),
            )
        ),
        delivery_gate=StrictDeliverySafetyGate(),
        outbox=InMemoryDeliveryOutbox(),
        safety_audit_journal=first.safety_audit_journal,
    )
    await output_runner.run_once(_NOW)
    await delivery_runner.run_once(_NOW)
    await first.close()

    restarted = wire_runtime_state(config)
    try:
        count = await restarted.safety_audit_journal.recent_block_count(
            _TARGET_KEY,
            since=_NOW - timedelta(minutes=5),
        )
    finally:
        await restarted.close()

    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT observation_id, stage, allowed, reason
            FROM safety_audit_records
            ORDER BY observation_id
            """
        ).fetchall()

    assert count == 1
    assert rows == [
        ("obs-delivery", "delivery", 0, "proactive_sensitive_safety_context"),
        ("obs-output", "output", 0, "output_block"),
    ]


def _blocked_record(observation_id: str) -> SafetyAuditRecord:
    return SafetyAuditRecord(
        observation_id=ObservationId(observation_id),
        occurred_at=_NOW,
        stage=SafetyAuditStage.DELIVERY,
        allowed=False,
        reason="quiet_hours",
        risk_level=SafetyRiskLevel.MEDIUM,
        source=DeliverySource.PROACTIVE_IDLE_TICK,
        target_key=_TARGET_KEY,
        policy="strict_delivery",
        policy_version="1",
    )
