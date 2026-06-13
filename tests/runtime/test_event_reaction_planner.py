"""EventReactionPlanner tests。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.cognitive.workspace.frame import SituationContextSnapshot
from iris.contracts.activity import ActivityKind
from iris.contracts.availability import AvailabilitySnapshot, AvailabilityStatus
from iris.contracts.event_reaction import EventReactionKind
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActivityEventObservation,
    ObservationContext,
    ObservationKind,
)
from iris.core.ids import ActorId, ObservationId, SessionId
from iris.runtime.event_reaction.planner import EventReactionPlanner
from iris.runtime.event_reaction.policy import EventReactionPolicy, default_event_reaction_policy


@pytest.fixture
def planner() -> EventReactionPlanner:
    """デフォルトポリシーのEventReactionPlannerを提供する。

    Returns:
        EventReactionPlanner: テスト用planner。
    """
    return EventReactionPlanner(policy=default_event_reaction_policy())


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
        latest_activity=None,
        presence=None,
        space_occupancy=None,
        availability=AvailabilitySnapshot(
            actor_id=ActorId("actor-1"),
            status=availability_status,
            reason="test",
            observed_at=now,
            computed_at=now,
        ),
    )


def _activity(
    kind: ActivityKind,
    *,
    actor_id: ActorId,
    include_actor: bool = True,
) -> ActivityEventObservation:
    actor = (
        Identity(
            actor_id=actor_id,
            actor_kind=ActorKind.HUMAN,
            display_name="Actor",
        )
        if include_actor
        else None
    )
    return ActivityEventObservation(
        observation_id=ObservationId("obs-1"),
        session_id=SessionId("session-1"),
        context=ObservationContext(actor=actor, source="test"),
        occurred_at=datetime(2026, 6, 13, tzinfo=UTC),
        kind=ObservationKind.ACTIVITY_EVENT,
        activity_kind=kind,
    )


def test_voice_joined_available_returns_greeting(
    planner: EventReactionPlanner,
    actor_id: ActorId,
    now: datetime,
) -> None:
    """AVAILABLEなVOICE_JOINEDに対してgreeting候補を返す。"""
    decision = planner.plan(
        _activity(ActivityKind.VOICE_JOINED, actor_id=actor_id),
        situation_context=_situation(AvailabilityStatus.AVAILABLE, now=now),
    )

    assert decision.should_react is True
    assert decision.candidate is not None
    assert decision.candidate.kind is EventReactionKind.GREETING
    assert decision.candidate.text == "Welcome back."
    assert decision.candidate.priority == 10


def test_app_opened_available_returns_greeting(
    planner: EventReactionPlanner,
    actor_id: ActorId,
    now: datetime,
) -> None:
    """AVAILABLEなAPP_OPENEDに対してgreeting候補を返す。"""
    decision = planner.plan(
        _activity(ActivityKind.APP_OPENED, actor_id=actor_id),
        situation_context=_situation(AvailabilityStatus.AVAILABLE, now=now),
    )

    assert decision.should_react is True
    assert decision.candidate is not None
    assert decision.candidate.text == "Welcome back. I am here if you want to talk."
    assert decision.candidate.priority == 5


def test_app_opened_passive_rejected(
    planner: EventReactionPlanner,
    actor_id: ActorId,
    now: datetime,
) -> None:
    """APP_OPENEDはPASSIVEでは反応しない。"""
    decision = planner.plan(
        _activity(ActivityKind.APP_OPENED, actor_id=actor_id),
        situation_context=_situation(AvailabilityStatus.PASSIVE, now=now),
    )

    assert decision.should_react is False


def test_voice_left_rejected(
    planner: EventReactionPlanner,
    actor_id: ActorId,
    now: datetime,
) -> None:
    """VOICE_LEFTは反応しない。"""
    decision = planner.plan(
        _activity(ActivityKind.VOICE_LEFT, actor_id=actor_id),
        situation_context=_situation(AvailabilityStatus.AVAILABLE, now=now),
    )

    assert decision.should_react is False


def test_missing_actor_rejected(
    planner: EventReactionPlanner,
    actor_id: ActorId,
    now: datetime,
) -> None:
    """actorが未解決の場合は反応しない。"""
    decision = planner.plan(
        _activity(ActivityKind.VOICE_JOINED, actor_id=actor_id, include_actor=False),
        situation_context=_situation(AvailabilityStatus.AVAILABLE, now=now),
    )

    assert decision.should_react is False
    assert "actor not resolved" in decision.reason


def test_unknown_allowed_kind_without_candidate(
    actor_id: ActorId,
    now: datetime,
) -> None:
    """ポリシーで許可されていてもplannerに候補がないkindは反応しない。"""
    policy = EventReactionPolicy(
        kind_availability={
            ActivityKind.SYSTEM_INTERACTION: frozenset({AvailabilityStatus.AVAILABLE}),
        },
    )
    custom_planner = EventReactionPlanner(policy=policy)
    situation = SituationContextSnapshot(
        availability=AvailabilitySnapshot(
            actor_id=actor_id,
            status=AvailabilityStatus.AVAILABLE,
            reason="test",
            observed_at=now,
            computed_at=now,
        ),
    )

    decision = custom_planner.plan(
        _activity(ActivityKind.SYSTEM_INTERACTION, actor_id=actor_id),
        situation_context=situation,
    )

    assert decision.should_react is False
    assert "no deterministic candidate" in decision.reason
