from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.cognitive.affect.relationship import InMemoryRelationshipState, RelationshipStep
from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import AppraisalResult, StepStatus
from iris.cognitive.workspace.frame import WorkspaceFrame
from iris.contracts.identity import Identity
from iris.contracts.observations import ObservationKind, UserMessageObservation
from iris.core.ids import ExternalRef, ObservationId, SessionId, UserId


def user_message(actor: Identity | None = None) -> UserMessageObservation:
    return UserMessageObservation(
        observation_id=ObservationId("obs-relationship"),
        session_id=SessionId("session-relationship"),
        actor=actor,
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.USER_MESSAGE,
        text="thanks",
    )


@pytest.mark.anyio
async def test_relationship_step_updates_per_user_state() -> None:
    actor = Identity(
        user_id=UserId("user-relationship"),
        display_name="Mina",
        provider="test",
        provider_subject=ExternalRef("mina"),
    )
    state = InMemoryRelationshipState()
    builder = FrameBuilder()
    frame = WorkspaceFrame(observation=user_message(actor))
    frame = builder.apply(
        frame,
        AppraisalResult(step_name="appraisal", status=StepStatus.OK, valence=0.5),
    )

    result = await RelationshipStep(state).run(frame)
    enriched = builder.apply(frame, result)

    assert result.status == StepStatus.OK
    assert enriched.relationship.user_label == "Mina"
    assert enriched.relationship.affinity == 0.02
    assert enriched.relationship.trust == 0.515
    assert enriched.relationship.familiarity == 0.02
    assert enriched.relationship.relationship_summary is not None


@pytest.mark.anyio
async def test_relationship_step_skips_without_actor_identity() -> None:
    result = await RelationshipStep().run(WorkspaceFrame(observation=user_message()))

    assert result.status == StepStatus.SKIPPED
    assert result.reason == "no actor identity"
