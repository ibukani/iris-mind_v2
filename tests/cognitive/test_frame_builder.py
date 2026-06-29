"""FrameBuilder situation context tests."""

from __future__ import annotations

from datetime import UTC, datetime

from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.contracts.availability import AvailabilitySnapshot, AvailabilityStatus
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActorMessageObservation,
    ObservationContext,
    ObservationKind,
)
from iris.contracts.workspace_context import (
    ActorContextSnapshot,
    SituationContextSnapshot,
    SpaceContextSnapshot,
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


def _observation() -> ActorMessageObservation:
    """Build a simple observation for frame builder tests.

    Returns:
        ActorMessageObservation: A test observation.
    """
    return ActorMessageObservation(
        observation_id=ObservationId("obs-fb"),
        session_id=SessionId("session-fb"),
        context=ObservationContext(
            actor=Identity(
                actor_id=ActorId("actor-fb"),
                actor_kind=ActorKind.HUMAN,
                display_name="Mina",
                provider="test",
                provider_subject=ExternalRef("mina"),
            ),
            account_id=AccountId("account-fb"),
            device_id=DeviceId("device-fb"),
            space_id=SpaceId("space-fb"),
        ),
        occurred_at=datetime(2026, 6, 13, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text="hello",
    )


def test_build_initial_without_situation_context_is_compatible() -> None:
    """situation_context なしで build_initial が従来通り動作する。"""
    observation = _observation()
    frame = FrameBuilder.build_initial(observation)

    assert frame.observation is observation
    assert frame.actor_context == ActorContextSnapshot(
        actor=observation.context.actor,
        account_id=AccountId("account-fb"),
        device_id=DeviceId("device-fb"),
    )
    assert frame.space_context == SpaceContextSnapshot(space_id=SpaceId("space-fb"))
    assert frame.situation_context == SituationContextSnapshot()


def test_build_initial_with_situation_context_attaches_it() -> None:
    """build_initial に situation_context を渡すと WorkspaceFrame に紐づく。"""
    situation = SituationContextSnapshot(
        availability=AvailabilitySnapshot(
            actor_id=ActorId("actor-fb"),
            status=AvailabilityStatus.AVAILABLE,
            reason="test",
            observed_at=datetime(2026, 6, 13, tzinfo=UTC),
            computed_at=datetime(2026, 6, 13, tzinfo=UTC),
        ),
    )
    frame = FrameBuilder.build_initial(_observation(), situation_context=situation)

    assert frame.situation_context is situation
