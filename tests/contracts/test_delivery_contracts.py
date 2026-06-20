"""Delivery contract tests."""

from __future__ import annotations

from dataclasses import MISSING, fields

from iris.contracts.delivery import (
    TERMINAL_DELIVERY_STATUSES,
    DeliveryEnvelope,
    DeliveryRouteHint,
    DeliveryStatus,
    DeliveryTarget,
)
from iris.core.ids import ExternalRef, SessionId


def test_terminal_delivery_statuses_are_explicit() -> None:
    """Terminal delivery statuses are a named contract set."""
    assert {
        DeliveryStatus.SUCCEEDED,
        DeliveryStatus.FAILED_PERMANENT,
        DeliveryStatus.CANCELLED,
        DeliveryStatus.BLOCKED,
    } == TERMINAL_DELIVERY_STATUSES


def test_delivery_route_hint_preserves_provider_route() -> None:
    """Ingress route hint keeps provider routing outside ObservationContext."""
    hint = DeliveryRouteHint(
        provider="discord",
        provider_subject=ExternalRef("user-1"),
        provider_space_ref=ExternalRef("channel-1"),
        display_name="User",
    )
    assert hint.provider == "discord"
    assert hint.provider_subject == ExternalRef("user-1")


def test_delivery_target_can_hold_provider_route() -> None:
    """DeliveryTarget carries route fields needed at safety/outbox boundary."""
    target = DeliveryTarget(
        provider="discord",
        provider_subject=ExternalRef("user-1"),
        provider_space_ref=None,
        session_id=SessionId("session-1"),
    )
    assert target.provider_subject == ExternalRef("user-1")


def test_delivery_envelope_requires_idempotency_key_by_contract_use() -> None:
    """DeliveryEnvelope exposes idempotency key as a required constructor field."""
    field_by_name = {field.name: field for field in fields(DeliveryEnvelope)}
    idempotency_field = field_by_name["idempotency_key"]
    assert idempotency_field.default is MISSING
    assert idempotency_field.default_factory is MISSING
