"""Scheduler runner that submits observations through IrisRuntimeService."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from iris.contracts.actions import SendMessageAction
from iris.contracts.delivery import DeliveryEnvelope, DeliveryStatus, DeliveryTarget
from iris.core.ids import ActionId, CorrelationId, DeliveryId, ObservationId
from iris.runtime.ingress.observation_ingress import ObservationCapability
from iris.runtime.service import ObservationEnvelope, ObservationRuntimeService, RuntimeResponse
from iris.runtime.state.safety_audit import SafetyAuditRecord, SafetyAuditStage
from iris.safety.policy_engine import DeliverySource, SafetyPolicyContext, SafetyRiskLevel

if TYPE_CHECKING:
    from datetime import datetime

    from iris.contracts.availability import AvailabilitySnapshot
    from iris.runtime.delivery.outbox import DeliveryOutbox
    from iris.runtime.scheduler.models import ScheduledObservation
    from iris.runtime.scheduler.ports import DeliveryAvailabilityProvider, RuntimeScheduler
    from iris.runtime.state.safety_audit import SafetyAuditJournal
    from iris.safety.delivery_gate import DeliverySafetyDecision, DeliverySafetyGate


@dataclass(frozen=True)
class ScheduledObservationResult:
    """One scheduled observation dispatch result."""

    observation_id: ObservationId
    status: str
    reason: str
    delivery_id: DeliveryId | None = None


@dataclass(frozen=True)
class SchedulerRunResult:
    """A single scheduler run result."""

    started_at: datetime
    finished_at: datetime
    results: tuple[ScheduledObservationResult, ...]


@dataclass(frozen=True)
class SchedulerRunner:
    """Bridge RuntimeScheduler to IrisRuntimeService and DeliveryOutbox."""

    scheduler: RuntimeScheduler
    runtime_service: ObservationRuntimeService
    delivery_gate: DeliverySafetyGate
    outbox: DeliveryOutbox
    availability_provider: DeliveryAvailabilityProvider | None = None
    delivery_enabled: bool = True
    max_attempts: int = 3
    safety_audit_journal: SafetyAuditJournal | None = None
    recent_block_window_seconds: float = 1800.0

    async def run_once(self, now: datetime) -> SchedulerRunResult:
        """Dispatch due observations once without sleeping.

        Returns:
            全 scheduled observation の dispatch結果。
        """
        results: list[ScheduledObservationResult] = []
        due_observations = await self.scheduler.due_observations(now)
        for scheduled in due_observations:
            result = await self._run_one(scheduled, now)
            results.append(result)
        return SchedulerRunResult(started_at=now, finished_at=now, results=tuple(results))

    async def _run_one(
        self,
        scheduled: ScheduledObservation,
        now: datetime,
    ) -> ScheduledObservationResult:
        """Submit one scheduled observation and route its response.

        Returns:
            dispatch 成否と配送 enqueue 結果。
        """
        observation_id = scheduled.observation.observation_id
        try:
            response = await self.runtime_service.handle_observation(
                ObservationEnvelope.trusted_adapter(
                    observation=scheduled.observation,
                    adapter_id="runtime_scheduler",
                    provider="runtime",
                    capabilities={ObservationCapability.INTERNAL_EVENT},
                    correlation_id=scheduled.correlation_id,
                )
            )
        except (RuntimeError, ValueError) as exc:
            await self.scheduler.mark_failed(observation_id, failed_at=now, reason=str(exc))
            return ScheduledObservationResult(observation_id, "failed", str(exc))
        return await self._dispatch_response(scheduled, response, now)

    async def _dispatch_response(
        self,
        scheduled: ScheduledObservation,
        response: RuntimeResponse,
        now: datetime,
    ) -> ScheduledObservationResult:
        """Apply safety and enqueue sendable runtime response.

        Returns:
            no_send / blocked / enqueued の何れかの結果。

        Raises:
            RuntimeError: delivery target precondition check is inconsistent.
        """
        observation_id = scheduled.observation.observation_id
        if not response.output.is_sendable:
            await self.scheduler.mark_dispatched(observation_id, dispatched_at=now)
            reason = response.output.safety_block_reason or "output_not_sendable"
            if response.output.safety_block_reason is not None:
                await self._audit(
                    SafetyAuditRecord(
                        observation_id=observation_id,
                        occurred_at=now,
                        stage=SafetyAuditStage.OUTPUT,
                        allowed=False,
                        reason=reason,
                        source=_delivery_source(scheduled),
                        target_key=_optional_target_key(scheduled.target),
                        risk_level=SafetyRiskLevel.HIGH,
                        policy="output_safety",
                        policy_version="1",
                    )
                )
            return ScheduledObservationResult(observation_id, "no_send", reason)
        target = scheduled.target
        block_reason = _delivery_block_reason(
            delivery_enabled=self.delivery_enabled,
            has_target=target is not None,
        )
        if block_reason is not None:
            await self.scheduler.mark_dispatched(observation_id, dispatched_at=now)
            return ScheduledObservationResult(observation_id, "blocked", block_reason)
        if target is None:
            msg = "delivery target required after delivery block check"
            raise RuntimeError(msg)
        availability = await self._availability_for(target, now)
        target_key = _target_key(target)
        recent_block_count = await self._recent_block_count(target_key, now)
        decision = await self.delivery_gate.check(
            target=target,
            output=response.output,
            availability=availability,
            now=now,
            policy_context=SafetyPolicyContext(
                source=_delivery_source(scheduled),
                target_key=target_key,
                policy_constraint_names=response.output.policy_constraint_names,
                safety_contexts=response.output.safety_contexts,
                recent_block_count=recent_block_count,
            ),
        )
        await self._audit(
            SafetyAuditRecord(
                observation_id=observation_id,
                occurred_at=now,
                stage=SafetyAuditStage.DELIVERY,
                allowed=decision.allowed,
                reason=decision.reason,
                source=_delivery_source(scheduled),
                target_key=target_key,
                risk_level=decision.risk_level,
                policy=(decision.audit.policy if decision.audit is not None else "basic_delivery"),
                policy_version=(
                    decision.audit.policy_version if decision.audit is not None else "1"
                ),
            )
        )
        if not decision.allowed:
            await self.scheduler.mark_dispatched(observation_id, dispatched_at=now)
            return ScheduledObservationResult(observation_id, "blocked", decision.reason)
        return await self._enqueue_sendable(scheduled, response, decision, target, now)

    async def _recent_block_count(self, target_key: str, now: datetime) -> int:
        if self.safety_audit_journal is None:
            return 0
        since = now - timedelta(seconds=self.recent_block_window_seconds)
        return await self.safety_audit_journal.recent_block_count(target_key, since=since)

    async def _audit(self, record: SafetyAuditRecord) -> None:
        if self.safety_audit_journal is None:
            return
        await self.safety_audit_journal.append(record)

    async def _availability_for(
        self,
        target: DeliveryTarget,
        now: datetime,
    ) -> AvailabilitySnapshot | None:
        """Resolve availability for a target through the injected provider.

        Returns:
            可用性スナップショット。provider がない場合は None。
        """
        if self.availability_provider is None:
            return None
        return await self.availability_provider.availability_for_target(target, now=now)

    async def _enqueue_sendable(
        self,
        scheduled: ScheduledObservation,
        response: RuntimeResponse,
        decision: DeliverySafetyDecision,
        target: DeliveryTarget,
        now: datetime,
    ) -> ScheduledObservationResult:
        """Build and enqueue a delivery envelope for a sendable response.

        Returns:
            enqueue された delivery id を含む結果。
        """
        observation_id = scheduled.observation.observation_id
        correlation_id = (
            scheduled.correlation_id
            or response.correlation_id
            or CorrelationId(f"scheduler:{observation_id}")
        )
        action = SendMessageAction(
            action_id=ActionId(f"action:{observation_id}"),
            session_id=scheduled.observation.session_id,
            correlation_id=correlation_id,
            text=response.output.text or "",
        )
        envelope = DeliveryEnvelope(
            delivery_id=DeliveryId(f"delivery:{observation_id}"),
            action=action,
            target=target,
            status=DeliveryStatus.PENDING,
            created_at=now,
            updated_at=now,
            not_before=decision.not_before,
            attempts=0,
            max_attempts=self.max_attempts,
            idempotency_key=_idempotency_key(observation_id, target),
            source_observation_id=observation_id,
        )
        stored = await self.outbox.enqueue(envelope)
        await self.scheduler.mark_dispatched(observation_id, dispatched_at=now)
        return ScheduledObservationResult(
            observation_id,
            "enqueued",
            "delivery_enqueued",
            stored.delivery_id,
        )


def _idempotency_key(observation_id: ObservationId, target: DeliveryTarget) -> str:
    """Build deterministic delivery idempotency key.

    Returns:
        決定論的な idempotency key。
    """
    return (
        f"proactive:{observation_id}:{target.provider}:"
        f"{target.provider_subject}:{target.provider_space_ref}"
    )


def _delivery_source(scheduled: ScheduledObservation) -> DeliverySource:
    return scheduled.delivery_source or DeliverySource.PROACTIVE_IDLE_TICK


def _target_key(target: DeliveryTarget) -> str:
    return f"{target.provider}:{target.provider_subject or ''}:{target.provider_space_ref or ''}"


def _optional_target_key(target: DeliveryTarget | None) -> str:
    return _target_key(target) if target is not None else "unresolved"


def _delivery_block_reason(*, delivery_enabled: bool, has_target: bool) -> str | None:
    """Return delivery block reason before safety/enqueue.

    Returns:
        block reason, or None when delivery may proceed.
    """
    if not delivery_enabled:
        return "delivery_disabled"
    if not has_target:
        return "missing_delivery_target"
    return None
