"""StrictDeliverySafetyGate tests。"""

from __future__ import annotations

from datetime import UTC, datetime, time

import pytest

from iris.contracts.actions import PresentedOutput
from iris.contracts.availability import AvailabilitySnapshot, AvailabilityStatus
from iris.contracts.delivery import DeliveryTarget
from iris.core.ids import ExternalRef, SessionId
from iris.safety.delivery_gate import (
    BasicDeliverySafetyGate,
    DeliverySafetyDecision,
    QuietHoursPolicy,
    StrictDeliverySafetyGate,
)
from iris.safety.policy_engine import DeliverySource, SafetyPolicyContext, SafetyRiskLevel

pytestmark = pytest.mark.anyio
_NOW = datetime(2026, 1, 1, 23, tzinfo=UTC)


def _target() -> DeliveryTarget:
    return DeliveryTarget(
        provider="discord",
        provider_subject=ExternalRef("user-1"),
        provider_space_ref=None,
        session_id=SessionId("session-1"),
    )


async def test_strict_gate_blocks_sensitive_proactive_output() -> None:
    """Sensitive policy provenance blocks proactive delivery。"""
    decision = await StrictDeliverySafetyGate().check(
        target=_target(),
        output=PresentedOutput(text="safe rendered text"),
        availability=None,
        now=_NOW,
        policy_context=SafetyPolicyContext(
            source=DeliverySource.PROACTIVE_IDLE_TICK,
            target_key="target",
            policy_constraint_names=("sensitive_safety_context",),
        ),
    )
    assert decision.allowed is False
    assert decision.reason == "proactive_sensitive_safety_context"
    assert decision.audit is not None


async def test_strict_gate_rejects_invalid_target_before_policy_engine() -> None:
    """Strict gate はtarget/output precheck失敗をpolicy評価前に返す。"""
    target = DeliveryTarget(
        provider="discord",
        provider_subject=None,
        provider_space_ref=None,
        session_id=SessionId("session-1"),
    )
    decision = await StrictDeliverySafetyGate().check(
        target=target,
        output=PresentedOutput(text="hello"),
        availability=None,
        now=_NOW,
    )

    assert decision.allowed is False
    assert decision.reason == "missing_route"
    assert decision.audit is None


async def test_strict_gate_does_not_block_user_response_for_sensitive_context_alone() -> None:
    """User-initiated response は sensitive context だけでは block しない。"""
    decision = await StrictDeliverySafetyGate().check(
        target=_target(),
        output=PresentedOutput(text="supportive response"),
        availability=None,
        now=_NOW,
        policy_context=SafetyPolicyContext(
            source=DeliverySource.USER_INITIATED,
            target_key="target",
            policy_constraint_names=("sensitive_safety_context",),
        ),
    )
    assert decision.allowed is True


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (AvailabilityStatus.BUSY, "availability_busy"),
        (AvailabilityStatus.UNAVAILABLE, "availability_unavailable"),
    ],
)
async def test_strict_user_initiated_unavailable_status_is_blocked_like_basic(
    status: AvailabilityStatus,
    reason: str,
) -> None:
    """Strict gate は user-initiated delivery でも basic availability規則を維持する。"""
    availability = AvailabilitySnapshot(
        actor_id=None,
        status=status,
        reason=status.value,
        observed_at=_NOW,
        computed_at=_NOW,
    )
    decision = await StrictDeliverySafetyGate().check(
        target=_target(),
        output=PresentedOutput(text="hello"),
        availability=availability,
        now=_NOW,
        policy_context=SafetyPolicyContext(
            source=DeliverySource.USER_INITIATED,
            target_key="target",
        ),
    )
    assert decision.allowed is False
    assert decision.reason == reason


async def test_strict_gate_blocks_proactive_busy_and_quiet_hours() -> None:
    """Busy と quiet hours は proactive delivery を block する。"""
    gate = StrictDeliverySafetyGate(
        basic=BasicDeliverySafetyGate(
            quiet_hours=QuietHoursPolicy(enabled=True, start=time(22), end=time(8), timezone="UTC")
        )
    )
    availability = AvailabilitySnapshot(
        actor_id=None,
        status=AvailabilityStatus.BUSY,
        reason="busy",
        observed_at=_NOW,
        computed_at=_NOW,
    )
    context = SafetyPolicyContext(
        source=DeliverySource.PROACTIVE_IDLE_TICK,
        target_key="target",
    )
    busy = await gate.check(
        target=_target(),
        output=PresentedOutput(text="hello"),
        availability=availability,
        now=datetime(2026, 1, 1, 12, tzinfo=UTC),
        policy_context=context,
    )
    quiet = await gate.check(
        target=_target(),
        output=PresentedOutput(text="hello"),
        availability=None,
        now=_NOW,
        policy_context=context,
    )
    assert busy.reason == "availability_busy"
    assert busy.risk_level is SafetyRiskLevel.MEDIUM
    _assert_strict_audit(busy, source=DeliverySource.PROACTIVE_IDLE_TICK, target_key="target")
    assert quiet.reason == "quiet_hours"
    assert quiet.risk_level is SafetyRiskLevel.MEDIUM
    _assert_strict_audit(quiet, source=DeliverySource.PROACTIVE_IDLE_TICK, target_key="target")


async def test_strict_proactive_unavailable_has_strict_audit_metadata() -> None:
    """Proactive UNAVAILABLE block はstrict policy provenanceを保持する。"""
    availability = AvailabilitySnapshot(
        actor_id=None,
        status=AvailabilityStatus.UNAVAILABLE,
        reason="unavailable",
        observed_at=_NOW,
        computed_at=_NOW,
    )
    decision = await StrictDeliverySafetyGate().check(
        target=_target(),
        output=PresentedOutput(text="hello"),
        availability=availability,
        now=_NOW,
        policy_context=SafetyPolicyContext(
            source=DeliverySource.PROACTIVE_IDLE_TICK,
            target_key="target",
        ),
    )
    assert decision.reason == "availability_unavailable"
    assert decision.risk_level is SafetyRiskLevel.MEDIUM
    _assert_strict_audit(
        decision,
        source=DeliverySource.PROACTIVE_IDLE_TICK,
        target_key="target",
    )


def _assert_strict_audit(
    decision: DeliverySafetyDecision,
    *,
    source: DeliverySource,
    target_key: str,
) -> None:
    assert decision.audit is not None
    assert decision.audit.policy == "strict_delivery"
    assert decision.audit.policy_version == "1"
    assert decision.audit.source is source
    assert decision.audit.target_key == target_key
