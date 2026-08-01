"""StrictDeliverySafetyGate tests。"""

from __future__ import annotations

from datetime import UTC, datetime, time
from typing import override

import pytest

from iris.contracts.actions import PresentedOutput
from iris.contracts.availability import AvailabilitySnapshot, AvailabilityStatus
from iris.contracts.delivery import DeliverySurface, DeliveryTarget
from iris.contracts.presentation_hints import PresentationHints, PresentationModality
from iris.contracts.safety import (
    SafetyContext,
    SafetyContextCategory,
    SafetyContextReason,
    SafetyContextSeverity,
    SafetyContextSource,
    SafetyResponseDirective,
)
from iris.contracts.surface_policy import DeliverySurfacePolicy
from iris.contracts.user_control import DeliveryUserControlStore, UserControlState
from iris.contracts.verifier import (
    DeliveryVerifierAvailabilityResolver,
    VerifierAvailability,
    VerifierStatus,
)
from iris.core.ids import ExternalRef, SessionId
from iris.runtime.config.surface_policy import production_surface_policy
from iris.safety.delivery_gate import (
    BasicDeliverySafetyGate,
    DeliverySafetyDecision,
    ProductionDeliverySafetyGate,
    QuietHoursPolicy,
    StrictDeliverySafetyGate,
)
from iris.safety.policy_engine import DeliverySource, SafetyPolicyContext, SafetyRiskLevel

pytestmark = pytest.mark.anyio
_NOW = datetime(2026, 1, 1, 23, tzinfo=UTC)


class _StubUserControlStore(DeliveryUserControlStore):
    """テスト用の固定 user control store。"""

    def __init__(self, state: UserControlState | None) -> None:
        """固定状態を持つ stub を作成する。"""
        self._state = state

    @override
    async def get(self, target_key: str) -> UserControlState | None:
        """固定状態を返す。

        Returns:
            Stub に設定された制御状態。未設定なら None。
        """
        _ = target_key
        return self._state

    @override
    async def set(self, target_key: str, state: UserControlState) -> None:
        """固定状態を更新する。"""
        _ = target_key
        self._state = state


class _StubVerifierResolver(DeliveryVerifierAvailabilityResolver):
    """テスト用の固定 verifier availability resolver。"""

    def __init__(self, availability: VerifierAvailability) -> None:
        """固定 availability を持つ stub を作成する。"""
        self._availability = availability

    @override
    async def availability(self) -> VerifierAvailability:
        """固定 availability を返す。

        Returns:
            Stub に設定された VerifierAvailability。
        """
        return self._availability


def _verifier(status: VerifierStatus) -> VerifierAvailability:
    return VerifierAvailability(
        status=status,
        reason=status.value,
        observed_at=_NOW,
    )


def _user_state(**updates: bool) -> UserControlState:
    return UserControlState(updated_at=_NOW, **updates)


def _high_risk_context() -> SafetyContext:
    return SafetyContext(
        category=SafetyContextCategory.SELF_HARM,
        severity=SafetyContextSeverity.HIGH,
        source=SafetyContextSource.PROACTIVE,
        confidence=0.9,
        reasons=(SafetyContextReason(code="risk", description="static risk metadata"),),
        directive=SafetyResponseDirective.SAFE_REDIRECT,
    )


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


async def test_strict_gate_blocks_typed_high_risk_proactive_output() -> None:
    """Typed high-risk safety context は proactive delivery を block する。"""
    decision = await StrictDeliverySafetyGate().check(
        target=_target(),
        output=PresentedOutput(text="safe rendered text", safety_contexts=(_high_risk_context(),)),
        availability=None,
        now=_NOW,
        policy_context=SafetyPolicyContext(
            source=DeliverySource.PROACTIVE_IDLE_TICK,
            target_key="target",
            safety_contexts=(_high_risk_context(),),
        ),
    )

    assert decision.allowed is False
    assert decision.reason == "proactive_high_risk_safety_context"
    assert decision.risk_level is SafetyRiskLevel.HIGH


async def test_strict_gate_does_not_block_user_initiated_typed_support_context() -> None:
    """User-initiated delivery は typed high-risk context だけで blanket block しない。"""
    decision = await StrictDeliverySafetyGate().check(
        target=_target(),
        output=PresentedOutput(text="supportive response"),
        availability=None,
        now=_NOW,
        policy_context=SafetyPolicyContext(
            source=DeliverySource.USER_INITIATED,
            target_key="target",
            safety_contexts=(_high_risk_context(),),
        ),
    )

    assert decision.allowed is True


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

    unknown_surface = await ProductionDeliverySafetyGate().check(
        target=_target(),
        output=PresentedOutput(text="hello"),
        availability=None,
        now=_NOW,
    )
    assert unknown_surface.allowed is False
    assert unknown_surface.reason == "unknown_delivery_surface"
    assert unknown_surface.risk_level is SafetyRiskLevel.HIGH
    assert unknown_surface.audit is not None
    assert unknown_surface.audit.policy == "production_delivery"

    known_surface = await ProductionDeliverySafetyGate().check(
        target=_target().model_copy(update={"surface": DeliverySurface.PRIVATE_DIRECT_MESSAGE}),
        output=PresentedOutput(text="hello"),
        availability=None,
        now=_NOW,
    )
    assert known_surface.allowed is True


async def test_production_gate_applies_surface_policy() -> None:
    """Production gate は surface policy の deny/allow matrix を強制する。"""
    # deny list が public surface を拒否する。
    deny_gate = ProductionDeliverySafetyGate(
        surface_policy=DeliverySurfacePolicy(
            denied_surfaces=frozenset({DeliverySurface.PUBLIC_CHANNEL}),
        ),
    )
    public_target = _target().model_copy(
        update={
            "surface": DeliverySurface.PUBLIC_CHANNEL,
            "provider_space_ref": ExternalRef("guild-1"),
        },
    )
    denied = await deny_gate.check(
        target=public_target,
        output=PresentedOutput(text="hello"),
        availability=None,
        now=_NOW,
    )
    assert denied.allowed is False
    assert denied.reason == "surface_denied"
    assert denied.risk_level is SafetyRiskLevel.HIGH

    # allowlist に無い provider を拒否する。
    provider_gate = ProductionDeliverySafetyGate(
        surface_policy=DeliverySurfacePolicy(allowed_providers=frozenset({"discord"})),
    )
    denied_provider = await provider_gate.check(
        target=public_target.model_copy(update={"provider": "slack"}),
        output=PresentedOutput(text="hello"),
        availability=None,
        now=_NOW,
    )
    assert denied_provider.allowed is False
    assert denied_provider.reason == "provider_not_allowed"

    # policy が deny しない DM は許可する。
    allowed = await deny_gate.check(
        target=_target().model_copy(
            update={"surface": DeliverySurface.PRIVATE_DIRECT_MESSAGE},
        ),
        output=PresentedOutput(text="hello"),
        availability=None,
        now=_NOW,
    )
    assert allowed.allowed is True


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


async def test_production_gate_blocks_opt_out_user() -> None:
    """Opt-out 済み target への proactive delivery を block する。"""
    gate = ProductionDeliverySafetyGate(
        user_control_store=_StubUserControlStore(_user_state(opt_out=True)),
    )
    decision = await gate.check(
        target=_target().model_copy(
            update={"surface": DeliverySurface.PRIVATE_DIRECT_MESSAGE},
        ),
        output=PresentedOutput(text="hello"),
        availability=None,
        now=_NOW,
    )
    assert decision.allowed is False
    assert decision.reason == "user_opted_out"
    assert decision.risk_level is SafetyRiskLevel.HIGH
    assert decision.audit is not None
    assert decision.audit.policy == "production_delivery"


async def test_production_gate_blocks_muted_and_blocked_users() -> None:
    """Mute / block 済み target への proactive delivery を block する。"""
    for flag in ("muted", "blocked"):
        gate = ProductionDeliverySafetyGate(
            user_control_store=_StubUserControlStore(_user_state(**{flag: True})),
        )
        decision = await gate.check(
            target=_target().model_copy(
                update={"surface": DeliverySurface.PRIVATE_DIRECT_MESSAGE},
            ),
            output=PresentedOutput(text="hello"),
            availability=None,
            now=_NOW,
        )
        assert decision.allowed is False
        assert decision.reason == f"user_{flag}"


async def test_production_gate_blocks_interrupting_output_when_disallowed() -> None:
    """Interruption 拒否済み target への interruptible output を block する。"""
    gate = ProductionDeliverySafetyGate(
        user_control_store=_StubUserControlStore(
            _user_state(interruptions_allowed=False),
        ),
    )
    blocked = await gate.check(
        target=_target().model_copy(
            update={"surface": DeliverySurface.PRIVATE_DIRECT_MESSAGE},
        ),
        output=PresentedOutput(
            text="hello",
            presentation_hints=PresentationHints(interruptible=True),
        ),
        availability=None,
        now=_NOW,
    )
    assert blocked.allowed is False
    assert blocked.reason == "interruptions_disabled"

    non_interruptible = await gate.check(
        target=_target().model_copy(
            update={"surface": DeliverySurface.PRIVATE_DIRECT_MESSAGE},
        ),
        output=PresentedOutput(
            text="hello",
            presentation_hints=PresentationHints(interruptible=False),
        ),
        availability=None,
        now=_NOW,
    )
    assert non_interruptible.allowed is True


async def test_production_gate_allows_user_without_control_state() -> None:
    """制御状態が無い target は block しない。"""
    gate = ProductionDeliverySafetyGate(
        user_control_store=_StubUserControlStore(None),
    )
    decision = await gate.check(
        target=_target().model_copy(
            update={"surface": DeliverySurface.PRIVATE_DIRECT_MESSAGE},
        ),
        output=PresentedOutput(text="hello"),
        availability=None,
        now=_NOW,
    )
    assert decision.allowed is True


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (VerifierStatus.WARMING, "verifier_warming"),
        (VerifierStatus.BUSY, "verifier_busy"),
        (VerifierStatus.UNAVAILABLE, "verifier_unavailable"),
    ],
)
async def test_production_gate_blocks_when_verifier_unavailable(
    status: VerifierStatus,
    reason: str,
) -> None:
    """Final verifier 非可用時は deterministic に block する。"""
    gate = ProductionDeliverySafetyGate(
        final_verifier_enabled=True,
        verifier_availability=_StubVerifierResolver(_verifier(status)),
    )
    decision = await gate.check(
        target=_target().model_copy(
            update={"surface": DeliverySurface.PRIVATE_DIRECT_MESSAGE},
        ),
        output=PresentedOutput(text="hello"),
        availability=None,
        now=_NOW,
    )
    assert decision.allowed is False
    assert decision.reason == reason
    assert decision.risk_level is SafetyRiskLevel.HIGH


async def test_production_gate_allows_when_verifier_available() -> None:
    """Final verifier 可用時は block しない。"""
    gate = ProductionDeliverySafetyGate(
        final_verifier_enabled=True,
        verifier_availability=_StubVerifierResolver(_verifier(VerifierStatus.AVAILABLE)),
    )
    decision = await gate.check(
        target=_target().model_copy(
            update={"surface": DeliverySurface.PRIVATE_DIRECT_MESSAGE},
        ),
        output=PresentedOutput(text="hello"),
        availability=None,
        now=_NOW,
    )
    assert decision.allowed is True


async def test_production_gate_verifier_check_is_skipped_when_disabled() -> None:
    """Final verifier 無効時は resolver を呼ばず通過する。"""
    gate = ProductionDeliverySafetyGate(
        final_verifier_enabled=False,
        verifier_availability=_StubVerifierResolver(_verifier(VerifierStatus.UNAVAILABLE)),
    )
    decision = await gate.check(
        target=_target().model_copy(
            update={"surface": DeliverySurface.PRIVATE_DIRECT_MESSAGE},
        ),
        output=PresentedOutput(text="hello"),
        availability=None,
        now=_NOW,
    )
    assert decision.allowed is True


async def test_production_gate_fails_closed_when_verifier_resolver_missing() -> None:
    """Final verifier 有効で resolver 未構成なら fail closed する。"""
    gate = ProductionDeliverySafetyGate(final_verifier_enabled=True)
    decision = await gate.check(
        target=_target().model_copy(
            update={"surface": DeliverySurface.PRIVATE_DIRECT_MESSAGE},
        ),
        output=PresentedOutput(text="hello"),
        availability=None,
        now=_NOW,
    )
    assert decision.allowed is False
    assert decision.reason == "verifier_not_configured"
    assert decision.risk_level is SafetyRiskLevel.HIGH


async def test_production_gate_unknown_surface_ignores_voice_modality_hint() -> None:
    """Presentation hint の modality は UNKNOWN surface を昇格させない (AC9)。"""
    for modality in (PresentationModality.VOICE, PresentationModality.NOTIFICATION):
        gate = ProductionDeliverySafetyGate(
            surface_policy=DeliverySurfacePolicy(
                denied_surfaces=frozenset({DeliverySurface.PUBLIC_CHANNEL}),
            ),
        )
        decision = await gate.check(
            target=_target(),
            output=PresentedOutput(
                text="hello",
                presentation_hints=PresentationHints(modality=modality),
            ),
            availability=None,
            now=_NOW,
        )
        assert decision.allowed is False
        assert decision.reason == "unknown_delivery_surface"


async def test_production_gate_denies_voice_and_avatar_surfaces() -> None:
    """Default production policy は voice / avatar surface を deny する。"""
    gate = ProductionDeliverySafetyGate(surface_policy=production_surface_policy().to_policy())
    for surface in (DeliverySurface.VOICE, DeliverySurface.AVATAR):
        decision = await gate.check(
            target=_target().model_copy(update={"surface": surface}),
            output=PresentedOutput(text="hello"),
            availability=None,
            now=_NOW,
        )
        assert decision.allowed is False
        assert decision.reason == "surface_denied"


async def test_production_gate_blocks_user_control_even_for_notification_modality() -> None:
    """User control block は surface 判定後・modality 非依存で適用される。"""
    gate = ProductionDeliverySafetyGate(
        surface_policy=DeliverySurfacePolicy(
            denied_surfaces=frozenset({DeliverySurface.PUBLIC_CHANNEL}),
        ),
        user_control_store=_StubUserControlStore(_user_state(blocked=True)),
    )
    decision = await gate.check(
        target=_target().model_copy(
            update={"surface": DeliverySurface.NOTIFICATION},
        ),
        output=PresentedOutput(
            text="hello",
            presentation_hints=PresentationHints(modality=PresentationModality.NOTIFICATION),
        ),
        availability=None,
        now=_NOW,
    )
    assert decision.allowed is False
    assert decision.reason == "user_blocked"
