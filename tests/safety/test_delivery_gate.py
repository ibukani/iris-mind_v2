"""Delivery safety gate tests."""

from __future__ import annotations

from datetime import UTC, datetime, time

import pytest

from iris.contracts.actions import PresentedOutput
from iris.contracts.availability import AvailabilitySnapshot, AvailabilityStatus
from iris.contracts.delivery import DeliveryTarget
from iris.core.ids import ActorId, ExternalRef, SessionId
from iris.safety.delivery_gate import BasicDeliverySafetyGate, QuietHoursPolicy

pytestmark = pytest.mark.anyio


def _target() -> DeliveryTarget:
    return DeliveryTarget(
        provider="discord",
        provider_subject=ExternalRef("user-1"),
        provider_space_ref=None,
        session_id=SessionId("session-1"),
    )


def _availability(status: AvailabilityStatus) -> AvailabilitySnapshot:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return AvailabilitySnapshot(
        actor_id=ActorId("actor-1"),
        status=status,
        reason=status.value,
        observed_at=now,
        computed_at=now,
    )


async def test_empty_output_is_blocked() -> None:
    """Non-sendable PresentedOutput is blocked."""
    decision = await BasicDeliverySafetyGate().check(
        target=_target(),
        output=PresentedOutput(text=None),
        availability=None,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert decision.allowed is False
    assert decision.reason == "output_not_sendable"


async def test_missing_provider_is_blocked() -> None:
    """Empty provider is blocked."""
    target = DeliveryTarget("", ExternalRef("user-1"), None, SessionId("session-1"))
    decision = await BasicDeliverySafetyGate().check(
        target=target,
        output=PresentedOutput(text="hello"),
        availability=None,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert decision.reason == "missing_provider"


async def test_missing_route_is_blocked() -> None:
    """Missing subject and space route is blocked."""
    target = DeliveryTarget("discord", None, None, SessionId("session-1"))
    decision = await BasicDeliverySafetyGate().check(
        target=target,
        output=PresentedOutput(text="hello"),
        availability=None,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert decision.reason == "missing_route"


async def test_quiet_hours_block_delivery() -> None:
    """Quiet hours blocks deterministic delivery."""
    gate = BasicDeliverySafetyGate(
        quiet_hours=QuietHoursPolicy(enabled=True, start=time(22), end=time(8), timezone="UTC")
    )
    decision = await gate.check(
        target=_target(),
        output=PresentedOutput(text="hello"),
        availability=None,
        now=datetime(2026, 1, 1, 23, tzinfo=UTC),
    )
    assert decision.reason == "quiet_hours"


async def test_available_target_is_allowed() -> None:
    """Available target with sendable output is allowed."""
    decision = await BasicDeliverySafetyGate().check(
        target=_target(),
        output=PresentedOutput(text="hello"),
        availability=_availability(AvailabilityStatus.AVAILABLE),
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert decision.allowed is True


async def test_busy_and_unavailable_block_delivery() -> None:
    """BUSY and UNAVAILABLE availability both block delivery."""
    gate = BasicDeliverySafetyGate()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    busy = await gate.check(
        target=_target(),
        output=PresentedOutput(text="hello"),
        availability=_availability(AvailabilityStatus.BUSY),
        now=now,
    )
    unavailable = await gate.check(
        target=_target(),
        output=PresentedOutput(text="hello"),
        availability=_availability(AvailabilityStatus.UNAVAILABLE),
        now=now,
    )
    assert busy.reason == "availability_busy"
    assert unavailable.reason == "availability_unavailable"
