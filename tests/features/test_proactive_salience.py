from __future__ import annotations

from datetime import UTC, datetime

from iris.cognitive.workspace.frame import (
    AffectSnapshot,
    MemorySummary,
    RelationshipSnapshot,
    WorkspaceFrame,
)
from iris.contracts.memory import MemoryId, MemoryRecord, MemorySearchResult
from iris.contracts.observations import IdleTickObservation, ObservationKind
from iris.contracts.policy import PolicyConstraint
from iris.core.ids import ObservationId, SessionId, UserId
from iris.features.proactive_talk.scoring import SalienceScorer


def _idle_frame(
    idle_seconds: float,
    *,
    memory: bool = False,
    familiarity: float | None = None,
    affect: AffectSnapshot | None = None,
    constraints: tuple[PolicyConstraint, ...] = (),
) -> WorkspaceFrame:
    memory_summary = MemorySummary()
    if memory:
        memory_summary = MemorySummary(
            retrieved_memories=(
                MemorySearchResult(
                    record=MemoryRecord(
                        id=MemoryId("memory-proactive"),
                        text="quiet room context",
                        subject_id=UserId("user-proactive"),
                    ),
                    score=0.8,
                ),
            )
        )

    relationship = RelationshipSnapshot()
    if familiarity is not None:
        relationship = RelationshipSnapshot(user_label="Mina", familiarity=familiarity)

    return WorkspaceFrame(
        observation=IdleTickObservation(
            observation_id=ObservationId("obs-proactive-salience"),
            session_id=SessionId("session-proactive-salience"),
            actor=None,
            occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
            kind=ObservationKind.IDLE_TICK,
            idle_seconds=idle_seconds,
        ),
        memory_summary=memory_summary,
        affect=affect or AffectSnapshot(),
        relationship=relationship,
        constraints=constraints,
    )


def test_salience_scoring_is_deterministic_and_bounded() -> None:
    frame = _idle_frame(600.0, memory=True, familiarity=0.8)
    scorer = SalienceScorer(threshold=0.5)

    first = scorer.score(frame)
    second = scorer.score(frame)

    assert first == second
    assert first.score == 0.9
    assert first.should_speak is True


def test_low_familiarity_and_negative_affect_reduce_salience() -> None:
    frame = _idle_frame(
        300.0,
        familiarity=0.0,
        affect=AffectSnapshot(arousal=0.9, valence=-0.8),
    )

    salience = SalienceScorer(threshold=0.5).score(frame)

    assert salience.score == 0.0
    assert salience.should_speak is False
    assert "low_familiarity" in salience.reasons
    assert "negative_high_arousal" in salience.reasons


def test_policy_block_prevents_proactive_speaking() -> None:
    frame = _idle_frame(
        600.0,
        constraints=(
            PolicyConstraint(
                name="policy_block",
                reason="test",
                blocks_response=True,
            ),
        ),
    )

    salience = SalienceScorer(threshold=0.5).score(frame)

    assert salience.blocked is True
    assert salience.should_speak is False
    assert salience.reasons == ("policy_block",)
