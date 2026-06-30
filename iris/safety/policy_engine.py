"""決定論的な runtime safety policy engine。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

from iris.contracts.availability import AvailabilityStatus


class SafetyRiskLevel(StrEnum):
    """Safety decision の決定論的な risk level。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DeliverySource(StrEnum):
    """配送を開始した source。"""

    USER_INITIATED = "user_initiated"
    PROACTIVE_IDLE_TICK = "proactive_idle_tick"


@dataclass(frozen=True)
class SafetyAuditMetadata:
    """Raw content を含まない監査用 metadata。"""

    policy: str
    policy_version: str
    source: DeliverySource
    target_key: str


@dataclass(frozen=True)
class SafetyPolicyContext:
    """Safety policy 評価に必要な型付き context。"""

    source: DeliverySource
    target_key: str
    policy_constraint_names: tuple[str, ...] = ()
    availability_status: AvailabilityStatus | None = None
    in_quiet_hours: bool = False
    recent_block_count: int = 0


@dataclass(frozen=True)
class SafetyPolicyDecision:
    """決定論的 safety policy の構造化結果。"""

    allowed: bool
    reason: str
    risk_level: SafetyRiskLevel
    not_before: datetime | None
    audit: SafetyAuditMetadata


@dataclass(frozen=True)
class SafetyPolicyEngine:
    """外部サービスを使わず strict policy を評価する。"""

    repeated_block_threshold: int = 2

    def evaluate_delivery(self, context: SafetyPolicyContext) -> SafetyPolicyDecision:
        """配送 context を固定順で評価する。

        Returns:
            最初に一致した規則の構造化 decision。
        """
        audit = SafetyAuditMetadata(
            policy="strict_delivery",
            policy_version="1",
            source=context.source,
            target_key=context.target_key,
        )
        block = self._proactive_block(context)
        if block is None:
            return _allow(audit)
        reason, risk_level = block
        return _block(reason, risk_level, audit)

    def _proactive_block(
        self,
        context: SafetyPolicyContext,
    ) -> tuple[str, SafetyRiskLevel] | None:
        if context.source is not DeliverySource.PROACTIVE_IDLE_TICK:
            return None
        checks = (
            (
                "sensitive_safety_context" in context.policy_constraint_names,
                "proactive_sensitive_safety_context",
                SafetyRiskLevel.HIGH,
            ),
            (
                context.availability_status is AvailabilityStatus.BUSY,
                "availability_busy",
                SafetyRiskLevel.MEDIUM,
            ),
            (
                context.availability_status is AvailabilityStatus.UNAVAILABLE,
                "availability_unavailable",
                SafetyRiskLevel.MEDIUM,
            ),
            (context.in_quiet_hours, "quiet_hours", SafetyRiskLevel.MEDIUM),
            (
                context.recent_block_count >= self.repeated_block_threshold,
                "repeated_recent_blocks",
                SafetyRiskLevel.MEDIUM,
            ),
        )
        for blocked, reason, risk_level in checks:
            if blocked:
                return reason, risk_level
        return None


def _allow(audit: SafetyAuditMetadata) -> SafetyPolicyDecision:
    return SafetyPolicyDecision(
        allowed=True,
        reason="allowed",
        risk_level=SafetyRiskLevel.LOW,
        not_before=None,
        audit=audit,
    )


def _block(
    reason: str,
    risk_level: SafetyRiskLevel,
    audit: SafetyAuditMetadata,
) -> SafetyPolicyDecision:
    return SafetyPolicyDecision(
        allowed=False,
        reason=reason,
        risk_level=risk_level,
        not_before=None,
        audit=audit,
    )
