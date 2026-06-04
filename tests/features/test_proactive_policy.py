"""Tests for proactive policy constraint generation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest

from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.workspace.frame import AffectSnapshot, RelationshipSnapshot, WorkspaceFrame
from iris.contracts.observations import IdleTickObservation, ObservationKind
from iris.core.ids import ObservationId, SessionId
from iris.features.proactive_talk.definition import ProactivePolicyStep
from iris.features.proactive_talk.policy import proactive_policy_constraints

if TYPE_CHECKING:
    from iris.features.proactive_talk.models import ProactiveFrameContext


def _idle_frame() -> WorkspaceFrame:
    """Return a WorkspaceFrame with an IdleTickObservation and affect/relationship data."""
    return WorkspaceFrame(
        observation=IdleTickObservation(
            observation_id=ObservationId("obs-proactive-policy"),
            session_id=SessionId("session-proactive-policy"),
            actor=None,
            space_id=None,
            occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
            kind=ObservationKind.IDLE_TICK,
            idle_seconds=600.0,
        ),
        affect=AffectSnapshot(arousal=0.9, valence=-0.8),
        relationship=RelationshipSnapshot(user_label="Mina", familiarity=0.0),
    )


def test_proactive_policy_constraints_are_typed_and_deterministic() -> None:
    """Verify proactive policy constraints are deterministic and typed."""
    frame = cast("ProactiveFrameContext", _idle_frame())

    first = proactive_policy_constraints(frame)
    second = proactive_policy_constraints(frame)

    assert first == second
    assert [constraint.name for constraint in first] == [
        "proactive_low_familiarity",
        "proactive_calm_response",
    ]
    assert [constraint.prompt_instruction for constraint in first] == [
        "avoid over-familiarity",
        "keep tone calm",
    ]


@pytest.mark.anyio
async def test_proactive_policy_step_enriches_frame_through_builder() -> None:
    """Verify ProactivePolicyStep enriches the frame with constraints through FrameBuilder."""
    frame = _idle_frame()
    result = await ProactivePolicyStep().run(frame)

    next_frame = FrameBuilder().apply(frame, result)

    assert frame.constraints == ()
    assert [constraint.name for constraint in next_frame.constraints] == [
        "proactive_low_familiarity",
        "proactive_calm_response",
    ]
    assert next_frame.action_preferences[0].name == "prefer_calm_proactive_talk"
