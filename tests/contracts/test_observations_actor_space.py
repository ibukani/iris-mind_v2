"""Observation context contract tests."""

from __future__ import annotations

from datetime import UTC, datetime

from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActorMessageObservation,
    IdleTickObservation,
    ObservationContext,
    ObservationKind,
)
from iris.core.ids import (
    AccountId,
    ActorId,
    DeviceId,
    ExternalRef,
    ObservationId,
    SessionId,
    SpaceId,
)
from tests.helpers.immutability import assert_frozen_field


def _actor(kind: ActorKind = ActorKind.HUMAN, actor_id: str = "actor-1") -> Identity:
    """Build a test identity.

    Returns:
        Identity for observation context tests.
    """
    return Identity(
        actor_id=ActorId(actor_id),
        actor_kind=kind,
        display_name="Mina",
        provider="test",
        provider_subject=ExternalRef("mina"),
    )


def test_actor_message_observation_uses_observation_context() -> None:
    """ActorMessageObservation carries actor and space through context."""
    observation = ActorMessageObservation(
        observation_id=ObservationId("obs-1"),
        session_id=SessionId("session-1"),
        context=ObservationContext(
            actor=_actor(),
            account_id=AccountId("account-1"),
            device_id=DeviceId("device-1"),
            space_id=SpaceId("space-dm-1"),
            source="test",
            metadata={"provider": "test"},
        ),
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text="hello",
        external_message_id=ExternalRef("msg-1"),
    )

    assert observation.context.actor is not None
    assert observation.context.actor.actor_kind is ActorKind.HUMAN
    assert observation.context.account_id == AccountId("account-1")
    assert observation.context.device_id == DeviceId("device-1")
    assert observation.context.space_id == SpaceId("space-dm-1")
    assert observation.context.source == "test"
    assert observation.context.metadata == {"provider": "test"}


def test_idle_tick_observation_uses_observation_context() -> None:
    """IdleTickObservation carries system actor and space through context."""
    observation = IdleTickObservation(
        observation_id=ObservationId("obs-2"),
        session_id=SessionId("session-2"),
        context=ObservationContext(
            actor=_actor(kind=ActorKind.SYSTEM, actor_id="system-clock"),
            space_id=SpaceId("space-room-1"),
        ),
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.IDLE_TICK,
        reason="scheduled",
        idle_seconds=12.5,
    )

    assert observation.context.actor is not None
    assert observation.context.actor.actor_id == ActorId("system-clock")
    assert observation.context.space_id == SpaceId("space-room-1")


def test_observation_requires_context_argument() -> None:
    """Observation subclasses require ObservationContext."""
    assert ActorMessageObservation.model_fields["context"].is_required()


def test_observation_has_no_direct_actor_or_space_fields() -> None:
    """Observation no longer exposes actor or space_id fields directly."""
    observation = ActorMessageObservation(
        observation_id=ObservationId("obs-3"),
        session_id=SessionId("session-3"),
        context=ObservationContext(actor=_actor(), space_id=SpaceId("space-1")),
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text="hello",
    )

    assert not hasattr(observation, "actor")
    assert not hasattr(observation, "space_id")


def test_observation_context_is_frozen() -> None:
    """ObservationContext is immutable."""
    context = ObservationContext(actor=_actor())

    assert_frozen_field(context, "actor", None)
