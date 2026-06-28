"""EventReactionDecisionPipeline tests。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.cognitive.workspace.frame import SituationContextSnapshot
from iris.contracts.activity import ActivityKind
from iris.contracts.availability import AvailabilitySnapshot, AvailabilityStatus
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActivityEventObservation,
    ObservationContext,
    ObservationKind,
)
from iris.core.ids import ActorId, ObservationId, SessionId
from iris.features.event_reaction.planner import EventReactionPlanner
from iris.features.event_reaction.policy import default_event_reaction_policy
from iris.features.event_reaction.templates import EventReactionTemplateProvider
from iris.runtime.ingress.event_reaction_decision_pipeline import EventReactionDecisionPipeline


@pytest.fixture
def pipeline() -> EventReactionDecisionPipeline:
    """デフォルトポリシーのEventReactionDecisionPipelineを提供する。

    Returns:
        EventReactionDecisionPipeline: テスト用pipeline。
    """
    template_provider = EventReactionTemplateProvider()
    return EventReactionDecisionPipeline(
        planners=(
            EventReactionPlanner(
                policy=default_event_reaction_policy(),
                template_provider=template_provider,
            ),
        ),
    )


@pytest.fixture
def actor_id() -> ActorId:
    """テスト用actor IDを提供する。

    Returns:
        ActorId: テスト用actor ID。
    """
    return ActorId("actor-1")


@pytest.fixture
def now() -> datetime:
    """テスト用現在時刻を提供する。

    Returns:
        datetime: テスト用現在時刻。
    """
    return datetime(2026, 6, 13, tzinfo=UTC)


def _situation(
    availability_status: AvailabilityStatus,
    *,
    now: datetime,
) -> SituationContextSnapshot:
    return SituationContextSnapshot(
        availability=AvailabilitySnapshot(
            actor_id=ActorId("actor-1"),
            status=availability_status,
            reason="test",
            observed_at=now,
            computed_at=now,
        ),
    )


def _activity(kind: ActivityKind, *, actor_id: ActorId, now: datetime) -> ActivityEventObservation:
    return ActivityEventObservation(
        observation_id=ObservationId("obs-1"),
        session_id=SessionId("session-1"),
        context=ObservationContext(
            actor=Identity(
                actor_id=actor_id,
                actor_kind=ActorKind.HUMAN,
                display_name="Actor",
            ),
            source="test",
        ),
        occurred_at=now,
        kind=ObservationKind.ACTIVITY_EVENT,
        activity_kind=kind,
    )


@pytest.mark.anyio
async def test_voice_joined_returns_reaction_candidate(
    pipeline: EventReactionDecisionPipeline,
    actor_id: ActorId,
    now: datetime,
) -> None:
    """VOICE_JOINEDが条件を満たせばReactionCandidateを返す。"""
    candidate = await pipeline.decide(
        _activity(ActivityKind.VOICE_JOINED, actor_id=actor_id, now=now),
        situation_context=_situation(AvailabilityStatus.AVAILABLE, now=now),
    )

    assert candidate is not None
    assert candidate.text == "Welcome back."
    assert candidate.priority == 10


@pytest.mark.anyio
async def test_app_opened_returns_reaction_candidate(
    pipeline: EventReactionDecisionPipeline,
    actor_id: ActorId,
    now: datetime,
) -> None:
    """APP_OPENEDが条件を満たせば対応するReactionCandidateを返す。"""
    candidate = await pipeline.decide(
        _activity(ActivityKind.APP_OPENED, actor_id=actor_id, now=now),
        situation_context=_situation(AvailabilityStatus.AVAILABLE, now=now),
    )

    assert candidate is not None
    assert candidate.text == "Welcome back. I am here if you want to talk."
    assert candidate.priority == 5


@pytest.mark.anyio
async def test_voice_left_returns_none(
    pipeline: EventReactionDecisionPipeline,
    actor_id: ActorId,
    now: datetime,
) -> None:
    """VOICE_LEFTは反応を生成しない。"""
    candidate = await pipeline.decide(
        _activity(ActivityKind.VOICE_LEFT, actor_id=actor_id, now=now),
        situation_context=_situation(AvailabilityStatus.AVAILABLE, now=now),
    )

    assert candidate is None
