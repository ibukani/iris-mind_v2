"""配送時刻・頻度・availability を検査する safety gate。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import TYPE_CHECKING, Protocol
from zoneinfo import ZoneInfo

from iris.contracts.availability import AvailabilityStatus
from iris.contracts.delivery import DeliverySurface
from iris.contracts.surface_policy import DeliverySurfacePolicy
from iris.contracts.verifier import (
    DeliveryVerifierAvailabilityResolver,
    VerifierStatus,
)
from iris.safety.policy_engine import (
    DeliverySource,
    SafetyAuditMetadata,
    SafetyPolicyContext,
    SafetyPolicyDecision,
    SafetyPolicyEngine,
    SafetyRiskLevel,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from iris.contracts.actions import PresentedOutput
    from iris.contracts.availability import AvailabilitySnapshot
    from iris.contracts.delivery import DeliveryTarget
    from iris.contracts.user_control import DeliveryUserControlStore


@dataclass(frozen=True)
class QuietHoursPolicy:
    """配送 quiet hours 設定。"""

    enabled: bool = False
    start: time = time(hour=22)
    end: time = time(hour=8)
    timezone: str = "Asia/Tokyo"


@dataclass(frozen=True)
class DeliverySafetyDecision:
    """配送 safety gate の決定。"""

    allowed: bool
    reason: str
    not_before: datetime | None = None
    risk_level: SafetyRiskLevel = SafetyRiskLevel.LOW
    audit: SafetyAuditMetadata | None = None


class DeliverySafetyGate(Protocol):
    """PresentedOutput を配送 outbox へ入れてよいか判定する port。"""

    async def check(
        self,
        *,
        target: DeliveryTarget,
        output: PresentedOutput,
        availability: AvailabilitySnapshot | None,
        now: datetime,
        policy_context: SafetyPolicyContext | None = None,
    ) -> DeliverySafetyDecision:
        """配送可否を決定する。

        Returns:
            DeliverySafetyDecision: 配送可否と理由。
        """
        ...


@dataclass(frozen=True)
class BasicDeliverySafetyGate:
    """決定論的な最小配送 safety gate。"""

    quiet_hours: QuietHoursPolicy = QuietHoursPolicy()

    async def check(
        self,
        *,
        target: DeliveryTarget,
        output: PresentedOutput,
        availability: AvailabilitySnapshot | None,
        now: datetime,
        policy_context: SafetyPolicyContext | None = None,
    ) -> DeliverySafetyDecision:
        """配送 target、availability、時刻から配送可否を返す。

        Returns:
            DeliverySafetyDecision: 配送可否と理由。blocked の場合は not_before を含む。
        """
        _ = policy_context
        precheck = self.check_target_output(target=target, output=output)
        if not precheck.allowed:
            return precheck
        reason = self._availability_reason(availability) or self._quiet_hours_reason(now)
        if reason is not None:
            return DeliverySafetyDecision(allowed=False, reason=reason)
        return DeliverySafetyDecision(allowed=True, reason="allowed")

    def check_target_output(
        self,
        *,
        target: DeliveryTarget,
        output: PresentedOutput,
    ) -> DeliverySafetyDecision:
        """Availability/time前にtargetとoutputだけを検証する。

        Returns:
            Target/outputの配送可否。
        """
        for reason in (self._output_reason(output), self._target_reason(target)):
            if reason is not None:
                return DeliverySafetyDecision(allowed=False, reason=reason)
        return DeliverySafetyDecision(allowed=True, reason="allowed")

    def is_quiet_hours(self, now: datetime) -> bool:
        """現在時刻が quiet hours 内なら True を返す。

        Returns:
            quiet hours 内なら True。
        """
        return self._quiet_hours_reason(now) is not None

    @staticmethod
    def _output_reason(output: PresentedOutput) -> str | None:
        """送信不可 output の理由を返す。

        Returns:
            block 理由または None。
        """
        if not output.is_sendable:
            return "output_not_sendable"
        return None

    @staticmethod
    def _target_reason(target: DeliveryTarget) -> str | None:
        """配送先 routing 不備の理由を返す。

        Returns:
            Block reason または None。
        """
        if not target.provider:
            return "missing_provider"
        if target.provider_subject is None and target.provider_space_ref is None:
            return "missing_route"
        return None

    @staticmethod
    def _availability_reason(availability: AvailabilitySnapshot | None) -> str | None:
        """可用性による block 理由を返す。

        Returns:
            Block reason または None。
        """
        if availability is None:
            return None
        return {
            AvailabilityStatus.BUSY: "availability_busy",
            AvailabilityStatus.UNAVAILABLE: "availability_unavailable",
        }.get(availability.status)

    def _quiet_hours_reason(self, now: datetime) -> str | None:
        """静寂時間帯内なら block 理由を返す。

        Returns:
            Block reason または None。
        """
        if not self.quiet_hours.enabled:
            return None
        local_now = now.astimezone(ZoneInfo(self.quiet_hours.timezone))
        current = local_now.time()
        start = self.quiet_hours.start
        end = self.quiet_hours.end
        in_window = start <= current < end if start < end else current >= start or current < end
        if in_window:
            return "quiet_hours"
        return None


@dataclass(frozen=True)
class StrictDeliverySafetyGate:
    """Basic checks と strict proactive policy を合成する gate。"""

    basic: BasicDeliverySafetyGate = BasicDeliverySafetyGate()
    engine: SafetyPolicyEngine = field(default_factory=SafetyPolicyEngine)

    async def check(
        self,
        *,
        target: DeliveryTarget,
        output: PresentedOutput,
        availability: AvailabilitySnapshot | None,
        now: datetime,
        policy_context: SafetyPolicyContext | None = None,
    ) -> DeliverySafetyDecision:
        """Basic validation 後に strict policy を評価する。

        Returns:
            配送可否、理由、risk、audit metadata。
        """
        precheck = self.basic.check_target_output(target=target, output=output)
        if not precheck.allowed:
            return precheck
        context = policy_context or SafetyPolicyContext(
            source=DeliverySource.USER_INITIATED,
            target_key=_target_key(target),
        )
        if context.source is DeliverySource.USER_INITIATED:
            return await self.basic.check(
                target=target,
                output=output,
                availability=availability,
                now=now,
            )
        availability_status = availability.status if availability is not None else None
        strict_context = SafetyPolicyContext(
            source=context.source,
            target_key=context.target_key,
            policy_constraint_names=context.policy_constraint_names,
            safety_contexts=context.safety_contexts,
            availability_status=availability_status,
            in_quiet_hours=self.basic.is_quiet_hours(now),
            recent_block_count=context.recent_block_count,
        )
        decision = self.engine.evaluate_delivery(strict_context)
        return _delivery_decision(decision)


@dataclass(frozen=True)
class ProductionDeliverySafetyGate:
    """Strict policyにsurface fail-closed検査を加えたproduction gate。"""

    strict: StrictDeliverySafetyGate = field(default_factory=StrictDeliverySafetyGate)
    surface_policy: DeliverySurfacePolicy = field(default_factory=DeliverySurfacePolicy)
    user_control_store: DeliveryUserControlStore | None = None
    final_verifier_enabled: bool = False
    verifier_availability: DeliveryVerifierAvailabilityResolver | None = None

    async def check(
        self,
        *,
        target: DeliveryTarget,
        output: PresentedOutput,
        availability: AvailabilitySnapshot | None,
        now: datetime,
        policy_context: SafetyPolicyContext | None = None,
    ) -> DeliverySafetyDecision:
        """未知 surface を配送 enqueue 前に拒否する。

        Presentation hints は surface の判定に使わない。target.surface が UNKNOWN のままなら
        fail closed し、hints による安全 policy の override を許さない。opt-out / mute /
        block / interruption 済み target と final verifier 非可用も block する。

        Returns:
            DeliverySafetyDecision: surface と strict policy に基づく配送判定。
        """
        block_reason = await self._production_block_reason(target, output)
        if block_reason is not None:
            return _blocked_production_decision(target, policy_context, block_reason)
        return await self.strict.check(
            target=target,
            output=output,
            availability=availability,
            now=now,
            policy_context=policy_context,
        )

    async def _production_block_reason(
        self,
        target: DeliveryTarget,
        output: PresentedOutput,
    ) -> str | None:
        """Production 追加検査の block 理由を順序付きで返す。

        Returns:
            最初に成立した block 理由。成立しなければ None。
        """
        if target.surface is DeliverySurface.UNKNOWN:
            return "unknown_delivery_surface"
        violation = self.surface_policy.surface_reason(
            surface=target.surface,
            provider=target.provider,
        )
        if violation is not None:
            return violation
        checks: tuple[Callable[[], Awaitable[str | None]], ...] = (
            lambda: self._user_control_reason(target, output),
            self._verifier_reason,
        )
        for check_reason in checks:
            reason = await check_reason()
            if reason is not None:
                return reason
        return None

    async def _user_control_reason(
        self,
        target: DeliveryTarget,
        output: PresentedOutput,
    ) -> str | None:
        """ユーザー制御状態による block 理由を返す。

        Returns:
            Block 理由または None。
        """
        if self.user_control_store is None:
            return None
        state = await self.user_control_store.get(_target_key(target))
        if state is None:
            return None
        if state.opt_out:
            reason = "user_opted_out"
        elif state.muted:
            reason = "user_muted"
        elif state.blocked:
            reason = "user_blocked"
        elif output.presentation_hints.interruptible and not state.interruptions_allowed:
            reason = "interruptions_disabled"
        else:
            return None
        return reason

    async def _verifier_reason(self) -> str | None:
        """Final verifier 非可用による block 理由を返す。

        Final verifier が有効なのに resolver が未構成の場合は fail-closed する。

        Returns:
            Block 理由または None。
        """
        if not self.final_verifier_enabled:
            return None
        if self.verifier_availability is None:
            return "verifier_not_configured"
        snapshot = await self.verifier_availability.availability()
        if snapshot.status is VerifierStatus.AVAILABLE:
            return None
        return {
            VerifierStatus.WARMING: "verifier_warming",
            VerifierStatus.BUSY: "verifier_busy",
            VerifierStatus.UNAVAILABLE: "verifier_unavailable",
        }[snapshot.status]


def _blocked_production_decision(
    target: DeliveryTarget,
    policy_context: SafetyPolicyContext | None,
    reason: str,
) -> DeliverySafetyDecision:
    source = policy_context.source if policy_context is not None else DeliverySource.USER_INITIATED
    return DeliverySafetyDecision(
        allowed=False,
        reason=reason,
        risk_level=SafetyRiskLevel.HIGH,
        audit=SafetyAuditMetadata(
            policy="production_delivery",
            policy_version="2",
            source=source,
            target_key=_target_key(target),
        ),
    )


def _delivery_decision(decision: SafetyPolicyDecision) -> DeliverySafetyDecision:
    return DeliverySafetyDecision(
        allowed=decision.allowed,
        reason=decision.reason,
        not_before=decision.not_before,
        risk_level=decision.risk_level,
        audit=decision.audit,
    )


def _target_key(target: DeliveryTarget) -> str:
    return f"{target.provider}:{target.provider_subject or ''}:{target.provider_space_ref or ''}"
