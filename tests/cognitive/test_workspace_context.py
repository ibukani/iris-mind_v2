"""Workspace context snapshot tests."""

from __future__ import annotations

from datetime import UTC, datetime

from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.workspace.frame import WorkspaceFrame
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActorMessageObservation,
    ObservationContext,
    ObservationKind,
)
from iris.contracts.workspace_context import (
    ActorContextSnapshot,
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
from tests.helpers.immutability import assert_frozen_field


def _observation() -> ActorMessageObservation:
    """Build an observation with full context.

    Returns:
        Actor message observation with actor, account, device, and space context.
    """
    return ActorMessageObservation(
        observation_id=ObservationId("obs-context"),
        session_id=SessionId("session-context"),
        context=ObservationContext(
            actor=Identity(
                actor_id=ActorId("actor-context"),
                actor_kind=ActorKind.HUMAN,
                display_name="Mina",
                provider="test",
                provider_subject=ExternalRef("mina"),
            ),
            account_id=AccountId("account-context"),
            device_id=DeviceId("device-context"),
            space_id=SpaceId("space-context"),
        ),
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text="hello",
    )


def test_workspace_frame_has_default_context_snapshots() -> None:
    """WorkspaceFrame exposes typed default context snapshots."""
    frame = WorkspaceFrame(observation=_observation())

    assert frame.actor_context == ActorContextSnapshot()
    assert frame.space_context == SpaceContextSnapshot()


def test_frame_builder_preserves_observation_context() -> None:
    """FrameBuilder copies observation context into WorkspaceFrame snapshots."""
    frame = FrameBuilder().build_initial(_observation())

    assert frame.actor_context.actor is not None
    assert frame.actor_context.actor.actor_id == ActorId("actor-context")
    assert frame.actor_context.account_id == AccountId("account-context")
    assert frame.actor_context.device_id == DeviceId("device-context")
    assert frame.space_context.space_id == SpaceId("space-context")
    assert frame.space_context.space is None
    assert frame.space_context.participant_actor_ids == ()


def test_workspace_context_snapshots_are_frozen() -> None:
    """Context snapshots are immutable."""
    assert_frozen_field(ActorContextSnapshot(), "account_id", AccountId("account-2"))
    assert_frozen_field(SpaceContextSnapshot(), "space_id", SpaceId("space-2"))
