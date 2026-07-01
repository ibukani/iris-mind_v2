"""Deterministic SafetyPolicyEngine tests。"""

from __future__ import annotations

from dataclasses import replace

from iris.contracts.availability import AvailabilityStatus
from iris.safety.policy_engine import (
    DeliverySource,
    SafetyPolicyContext,
    SafetyPolicyEngine,
    SafetyRiskLevel,
)


def _context() -> SafetyPolicyContext:
    return SafetyPolicyContext(
        source=DeliverySource.PROACTIVE_IDLE_TICK,
        target_key="discord:user-1:space-1",
    )


def test_sensitive_context_blocks_only_proactive_delivery() -> None:
    """Sensitive context は proactive delivery のみ block する。"""
    engine = SafetyPolicyEngine()
    proactive = engine.evaluate_delivery(
        replace(_context(), policy_constraint_names=("sensitive_safety_context",))
    )
    user = engine.evaluate_delivery(
        replace(
            _context(),
            source=DeliverySource.USER_INITIATED,
            policy_constraint_names=("sensitive_safety_context",),
        )
    )
    assert proactive.allowed is False
    assert proactive.reason == "proactive_sensitive_safety_context"
    assert proactive.risk_level is SafetyRiskLevel.HIGH
    assert user.allowed is True


def test_proactive_without_explicit_sensitive_provenance_is_not_sensitive_blocked() -> None:
    """Idle tickは過去user textからsensitive provenanceを暗黙生成しない。"""
    decision = SafetyPolicyEngine().evaluate_delivery(_context())

    assert decision.allowed is True
    assert decision.reason == "allowed"


def test_proactive_availability_quiet_hours_and_repeated_blocks_are_deterministic() -> None:
    """Strict proactive rules は固定優先順で評価する。"""
    engine = SafetyPolicyEngine(repeated_block_threshold=2)
    busy = engine.evaluate_delivery(
        replace(_context(), availability_status=AvailabilityStatus.BUSY)
    )
    quiet = engine.evaluate_delivery(replace(_context(), in_quiet_hours=True))
    repeated = engine.evaluate_delivery(replace(_context(), recent_block_count=2))
    assert busy.reason == "availability_busy"
    assert quiet.reason == "quiet_hours"
    assert repeated.reason == "repeated_recent_blocks"
    assert repeated.audit.target_key == "discord:user-1:space-1"
