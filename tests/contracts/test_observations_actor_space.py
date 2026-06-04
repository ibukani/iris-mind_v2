"""観測がactorとspace_idを運ぶことのテスト。"""

from __future__ import annotations

from datetime import UTC, datetime

from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActorMessageObservation,
    IdleTickObservation,
    ObservationKind,
)
from iris.core.ids import ActorId, ExternalRef, ObservationId, SessionId, SpaceId
from tests.helpers.immutability import assert_frozen_field


def _actor(kind: ActorKind = ActorKind.HUMAN, actor_id: str = "actor-1") -> Identity:
    """Build a test identity for observation construction.

    Returns:
        Identity: 観測テスト用のアクター中心のIdentity。
    """
    return Identity(
        actor_id=ActorId(actor_id),
        actor_kind=kind,
        display_name="Mina",
        provider="test",
        provider_subject=ExternalRef("mina"),
    )


def test_actor_message_observation_carries_actor_and_space_id() -> None:
    """ActorMessageObservation exposes actor and space_id fields at the base layer."""
    observation = ActorMessageObservation(
        observation_id=ObservationId("obs-1"),
        session_id=SessionId("session-1"),
        actor=_actor(),
        space_id=SpaceId("space-dm-1"),
        occurred_at=datetime(2026, 6, 4, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text="hello",
    )

    assert isinstance(observation.actor, Identity)
    assert observation.actor.actor_kind is ActorKind.HUMAN
    assert observation.space_id == SpaceId("space-dm-1")


def test_idle_tick_observation_carries_actor_and_space_id() -> None:
    """IdleTickObservation exposes actor and space_id fields at the base layer."""
    observation = IdleTickObservation(
        observation_id=ObservationId("obs-2"),
        session_id=SessionId("session-2"),
        actor=_actor(kind=ActorKind.SYSTEM, actor_id="system-clock"),
        space_id=SpaceId("space-room-1"),
        occurred_at=datetime(2026, 6, 4, tzinfo=UTC),
        kind=ObservationKind.IDLE_TICK,
        reason="quiet_room",
        idle_seconds=120.0,
    )

    assert observation.actor is not None
    assert observation.actor.actor_kind is ActorKind.SYSTEM
    assert observation.space_id == SpaceId("space-room-1")


def test_observation_actor_and_space_id_are_optional() -> None:
    """Observation accepts None for actor and space_id for source-agnostic construction."""
    observation = ActorMessageObservation(
        observation_id=ObservationId("obs-3"),
        session_id=SessionId("session-3"),
        actor=None,
        space_id=None,
        occurred_at=datetime(2026, 6, 4, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text="hello",
    )

    assert observation.actor is None
    assert observation.space_id is None


def test_observation_carries_iris_actor() -> None:
    """Observations can carry an Iris-self actor (e.g. internal events)."""
    iris_actor = Identity(
        actor_id=ActorId("iris-core"),
        actor_kind=ActorKind.IRIS,
        display_name="Iris",
        provider="iris",
        provider_subject=ExternalRef("iris-core"),
    )
    observation = IdleTickObservation(
        observation_id=ObservationId("obs-iris"),
        session_id=SessionId("session-iris"),
        actor=iris_actor,
        space_id=SpaceId("space-broadcast"),
        occurred_at=datetime(2026, 6, 4, tzinfo=UTC),
        kind=ObservationKind.IDLE_TICK,
        idle_seconds=0.0,
    )

    assert observation.actor is not None
    assert observation.actor.actor_kind is ActorKind.IRIS
    assert observation.actor.actor_id == ActorId("iris-core")


def test_observation_actor_and_space_id_are_frozen() -> None:
    """Observation's actor and space_id fields cannot be reassigned after construction."""
    observation = ActorMessageObservation(
        observation_id=ObservationId("obs-frozen"),
        session_id=SessionId("session-frozen"),
        actor=_actor(),
        space_id=SpaceId("space-1"),
        occurred_at=datetime(2026, 6, 4, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text="hello",
    )

    assert_frozen_field(observation, "actor", None)
    assert_frozen_field(observation, "space_id", SpaceId("space-replaced"))
