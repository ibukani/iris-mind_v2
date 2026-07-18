"""event reaction contract tests。"""

from __future__ import annotations

from datetime import UTC, datetime

from iris.contracts.activity import ActivityKind
from iris.contracts.availability import AvailabilitySnapshot, AvailabilityStatus
from iris.contracts.event_reaction import (
    EventReactionContext,
    EventReactionDecision,
)
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActivityEventObservation,
    ObservationContext,
    ObservationKind,
)
from iris.contracts.workspace_context import SituationContextSnapshot
from iris.core.ids import ActorId, ObservationId, SessionId


def test_event_reaction_decision_defaults_candidate_to_none() -> None:
    """EventReactionDecisionのcandidateがデフォルトでNoneであることを確認する。"""
    decision = EventReactionDecision(should_react=False, reason="no reaction")

    assert decision.candidate is None


def test_event_reaction_context_is_bounded_and_ignores_raw_metadata() -> None:
    """Prompt contextはdisplay name以外のraw ingress metadataを含めない。"""
    now = datetime(2026, 7, 18, tzinfo=UTC)
    observation = ActivityEventObservation(
        observation_id=ObservationId("observation-1"),
        session_id=SessionId("session-1"),
        context=ObservationContext(
            actor=Identity(
                actor_id=ActorId("actor-1"),
                actor_kind=ActorKind.HUMAN,
                display_name="A" * 200,
            ),
            source="provider",
            metadata={"raw_payload": "must not reach prompt"},
        ),
        occurred_at=now,
        kind=ObservationKind.ACTIVITY_EVENT,
        activity_kind=ActivityKind.VOICE_JOINED,
        metadata={"raw_payload": "must not reach prompt"},
    )
    context = EventReactionContext.from_observation(
        observation,
        SituationContextSnapshot(
            availability=AvailabilitySnapshot(
                actor_id=ActorId("actor-1"),
                status=AvailabilityStatus.AVAILABLE,
                reason="test",
                observed_at=now,
                computed_at=now,
            )
        ),
    )

    assert len(context.actor_display_name or "") == 80
    assert "raw_payload" not in context.model_dump_json()
    assert context.activity_kind is ActivityKind.VOICE_JOINED
