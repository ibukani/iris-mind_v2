"""EventReactionRunner tests。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.cognitive.workspace.frame import SituationContextSnapshot
from iris.contracts.activity import ActivityKind
from iris.contracts.availability import AvailabilitySnapshot, AvailabilityStatus
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActivityEventObservation,
    ActorMessageObservation,
    ObservationContext,
    ObservationKind,
)
from iris.core.ids import ActorId, ObservationId, SessionId
from iris.runtime.event_reaction.planner import EventReactionPlanner
from iris.runtime.event_reaction.policy import default_event_reaction_policy
from iris.runtime.event_reaction.runner import EventReactionRunner


@pytest.fixture
def runner() -> EventReactionRunner:
    """デフォルトポリシーのEventReactionRunnerを提供する。

    Returns:
        EventReactionRunner: テスト用runner。
    """
    return EventReactionRunner(
        planner=EventReactionPlanner(policy=default_event_reaction_policy()),
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
async def test_voice_joined_returns_presented_output(
    runner: EventReactionRunner,
    actor_id: ActorId,
    now: datetime,
) -> None:
    """VOICE_JOINEDが条件を満たせばevent_reactionなPresentedOutputを返す。"""
    output = await runner.react(
        _activity(ActivityKind.VOICE_JOINED, actor_id=actor_id, now=now),
        situation_context=_situation(AvailabilityStatus.AVAILABLE, now=now),
    )

    assert output is not None
    assert output.text == "Welcome back."
    assert output.style_hint == "event_reaction"
    assert output.priority == 10
    assert output.is_sendable


@pytest.mark.anyio
async def test_app_opened_returns_presented_output(
    runner: EventReactionRunner,
    actor_id: ActorId,
    now: datetime,
) -> None:
    """APP_OPENEDが条件を満たせば対応するPresentedOutputを返す。"""
    output = await runner.react(
        _activity(ActivityKind.APP_OPENED, actor_id=actor_id, now=now),
        situation_context=_situation(AvailabilityStatus.AVAILABLE, now=now),
    )

    assert output is not None
    assert output.text == "Welcome back. I am here if you want to talk."
    assert output.priority == 5


@pytest.mark.anyio
async def test_voice_left_returns_none(
    runner: EventReactionRunner,
    actor_id: ActorId,
    now: datetime,
) -> None:
    """VOICE_LEFTは反応を生成しない。"""
    output = await runner.react(
        _activity(ActivityKind.VOICE_LEFT, actor_id=actor_id, now=now),
        situation_context=_situation(AvailabilityStatus.AVAILABLE, now=now),
    )

    assert output is None


@pytest.mark.anyio
async def test_non_activity_observation_returns_none(
    runner: EventReactionRunner,
    actor_id: ActorId,
    now: datetime,
) -> None:
    """ActivityEventObservation以外には反応しない。"""
    observation = ActorMessageObservation(
        observation_id=ObservationId("obs-msg"),
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
        kind=ObservationKind.ACTOR_MESSAGE,
        text="hello",
    )

    output = await runner.react(
        observation,
        situation_context=_situation(AvailabilityStatus.AVAILABLE, now=now),
    )

    assert output is None
