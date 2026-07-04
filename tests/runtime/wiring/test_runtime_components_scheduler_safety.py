"""標準 runtime component wiring が scheduler safety dependencies を保持することを検証する。"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, override

import pytest

from iris.cognitive.cycle.models import ActionSelectionResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.contracts.actions import ActionPlan
from iris.contracts.delivery import DeliveryRouteHint, SchedulerTarget
from iris.contracts.presence import PresenceSnapshot, PresenceStatus
from iris.core.ids import AccountId, ActorId, ExternalRef, SessionId, SpaceId
from iris.runtime.app import IrisApp
from iris.runtime.config import IrisRuntimeConfig, RuntimeSafetyConfig, default_runtime_config
from iris.runtime.config.delivery import RuntimeDeliveryConfig, RuntimeQuietHoursConfig
from iris.runtime.scheduler.availability import DeliveryAvailabilityResolverAdapter
from iris.runtime.scheduler.runner import SchedulerRunner
from iris.runtime.state.safety_audit import InMemorySafetyAuditJournal, SafetyAuditStage
from iris.runtime.wiring.runtime import build_runtime_components
from iris.safety.delivery_gate import StrictDeliverySafetyGate
from iris.safety.policy_engine import DeliverySource

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.cognitive.workspace.frame import WorkspaceFrame
    from iris.features.definition import FeatureDefinition
    from iris.runtime.inference.scheduler import LocalInferenceResourceScheduler
    from iris.runtime.output_pipeline import RuntimeOutputPipeline
    from iris.runtime.wiring.app import AppStateDependencies
    from iris.runtime.wiring.llm import LLMClientFactory

pytestmark = pytest.mark.anyio

_NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
_ACTOR_ID = ActorId("actor-scheduler-busy")
_ACCOUNT_ID = AccountId("account-scheduler-busy")
_SPACE_ID = SpaceId("space-scheduler-busy")
_SESSION_ID = SessionId("session-scheduler-busy")


class _SendableStep(PipelineStep[ActionSelectionResult]):
    """送信可能な plan を返す scheduler composition test 用 step。"""

    name = "sendable"

    @override
    async def run(self, frame: WorkspaceFrame) -> ActionSelectionResult:
        """送信可能な ActionPlan を返す。

        Returns:
            ActionSelectionResult: 送信可能な text を持つ action plan。
        """
        _ = frame.observation
        return ActionSelectionResult(
            step_name=self.name,
            status=StepStatus.OK,
            action_plans=(
                ActionPlan(
                    turn_intent="respond",
                    candidate_text="scheduled hello",
                    should_respond=True,
                    priority=0,
                ),
            ),
        )


def _build_sendable_app(
    config: IrisRuntimeConfig,
    *,
    client_factory: LLMClientFactory | None = None,
    state: AppStateDependencies,
    output_pipeline: RuntimeOutputPipeline,
    features: Sequence[FeatureDefinition] = (),
    inference_scheduler: LocalInferenceResourceScheduler | None = None,
) -> IrisApp:
    """標準 composition の app だけを送信可能な test double に差し替える。

    Returns:
        送信可能な step を持つ IrisApp。
    """
    _ = config, client_factory, state, features, inference_scheduler
    return IrisApp(steps=(_SendableStep(),), output_pipeline=output_pipeline)


def test_build_runtime_components_wires_scheduler_safety_dependencies() -> None:
    """標準 RuntimeComponents で scheduler safety dependencies が欠落しない。"""
    components = build_runtime_components(default_runtime_config())

    assert isinstance(components.scheduler_runner, SchedulerRunner)
    provider = components.scheduler_runner.availability_provider
    assert isinstance(provider, DeliveryAvailabilityResolverAdapter)
    assert provider.presence_store is components.stores.presence_store
    assert provider.activity_projection_store is components.stores.activity_projection_store
    assert (
        components.scheduler_runner.safety_audit_journal is components.stores.safety_audit_journal
    )
    assert isinstance(components.stores.safety_audit_journal, InMemorySafetyAuditJournal)


def test_build_runtime_components_uses_strict_scheduler_delivery_gate() -> None:
    """標準 scheduler delivery gate に strict safety mode が反映される。"""
    config = replace(
        default_runtime_config(),
        safety=RuntimeSafetyConfig(mode="strict"),
    )

    components = build_runtime_components(config)

    assert isinstance(components.scheduler_runner.delivery_gate, StrictDeliverySafetyGate)


@pytest.mark.parametrize(
    ("presence_status", "delivery_config", "expected_reason"),
    [
        (PresenceStatus.DO_NOT_DISTURB, None, "availability_busy"),
        (PresenceStatus.OFFLINE, None, "availability_unavailable"),
        (
            None,
            RuntimeDeliveryConfig(
                quiet_hours=RuntimeQuietHoursConfig(
                    enabled=True,
                    start="11:00",
                    end="13:00",
                    timezone="UTC",
                ),
            ),
            "quiet_hours",
        ),
    ],
)
async def test_standard_runtime_wiring_blocks_safety_reasons_and_records_audit(
    monkeypatch: pytest.MonkeyPatch,
    presence_status: PresenceStatus | None,
    delivery_config: RuntimeDeliveryConfig | None,
    expected_reason: str,
) -> None:
    """標準 composition 経由で availability / quiet hours block が audit に残る。"""
    monkeypatch.setattr(
        "iris.runtime.wiring.runtime.build_app_from_config",
        _build_sendable_app,
    )
    base_config = default_runtime_config()
    config = replace(
        base_config,
        delivery=delivery_config or base_config.delivery,
        safety=RuntimeSafetyConfig(mode="strict"),
    )
    components = build_runtime_components(config)
    await components.stores.scheduler_target_store.upsert_target(_scheduler_target())
    if presence_status is not None:
        await components.stores.presence_store.update_presence(_presence(presence_status))

    result = await components.scheduler_runner.run_once(_NOW)

    assert result.results[0].status == "blocked"
    assert result.results[0].reason == expected_reason
    audit_journal = components.stores.safety_audit_journal
    assert isinstance(audit_journal, InMemorySafetyAuditJournal)
    records = audit_journal.records()
    assert len(records) == 1
    assert records[0].stage is SafetyAuditStage.DELIVERY
    assert not records[0].allowed
    assert records[0].reason == expected_reason
    assert records[0].source is DeliverySource.PROACTIVE_IDLE_TICK
    assert records[0].target_key == "discord:user-scheduler-busy:space-ref-scheduler-busy"


def _scheduler_target() -> SchedulerTarget:
    """BUSY の availability を解決できる scheduler target を作る。

    Returns:
        actor_id 付き SchedulerTarget。
    """
    return SchedulerTarget(
        actor_id=_ACTOR_ID,
        account_id=_ACCOUNT_ID,
        space_id=_SPACE_ID,
        session_id=_SESSION_ID,
        route=DeliveryRouteHint(
            provider="discord",
            provider_subject=ExternalRef("user-scheduler-busy"),
            provider_space_ref=ExternalRef("space-ref-scheduler-busy"),
            display_name="Busy User",
        ),
        display_name="Busy User",
        last_observed_at=_NOW - timedelta(seconds=1000),
        last_scheduler_attempt_at=None,
    )


def _presence(status: PresenceStatus) -> PresenceSnapshot:
    """Presence の snapshot を作る。

    Returns:
        AvailabilityResolver で block reason に変換される PresenceSnapshot。
    """
    return PresenceSnapshot(
        actor_id=_ACTOR_ID,
        account_id=_ACCOUNT_ID,
        device_id=None,
        source="test",
        status=status,
        observed_at=_NOW,
        received_at=_NOW,
        expires_at=_NOW + timedelta(minutes=5),
    )
