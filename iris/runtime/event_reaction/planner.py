"""イベント反応候補を決定論的に導出するplanner。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.activity import ActivityKind
from iris.contracts.event_reaction import (
    EventReactionDecision,
    EventReactionKind,
    ReactionCandidate,
)

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import SituationContextSnapshot
    from iris.contracts.availability import AvailabilitySnapshot, AvailabilityStatus
    from iris.contracts.observations import ActivityEventObservation
    from iris.runtime.event_reaction.policy import EventReactionPolicy

_VOICE_JOINED_TEXT = "Welcome back."

_APP_OPENED_TEXT = "Welcome back. I am here if you want to talk."


@dataclass(frozen=True)
class EventReactionPlanner:
    """ActivityEventObservationと状況contextから反応可否を決定する。"""

    policy: EventReactionPolicy

    def plan(
        self,
        observation: ActivityEventObservation,
        *,
        situation_context: SituationContextSnapshot,
    ) -> EventReactionDecision:
        """Activity kindとavailabilityに基づき決定論的な反応候補を返す。

        Args:
            observation: 反応対象のactivity event観測。
            situation_context: ランタイムから組み立てられた状況スナップショット。

        Returns:
            EventReactionDecision: 反応するかどうかの決定と候補。
        """
        if observation.context.actor_id is None:
            return EventReactionDecision(
                should_react=False,
                reason="actor not resolved",
            )

        status = _availability_status(situation_context.availability)
        if not self.policy.allows(observation.activity_kind, status):
            return EventReactionDecision(
                should_react=False,
                reason=(
                    f"{observation.activity_kind.value} not allowed "
                    f"for availability {_status_name(status)}"
                ),
            )

        candidate = _candidate_for(observation.activity_kind)
        if candidate is None:
            return EventReactionDecision(
                should_react=False,
                reason="no deterministic candidate",
            )

        return EventReactionDecision(
            should_react=True,
            reason="activity and availability allow reaction",
            candidate=candidate,
        )


def _availability_status(snapshot: AvailabilitySnapshot | None) -> AvailabilityStatus | None:
    return snapshot.status if snapshot is not None else None


def _status_name(status: AvailabilityStatus | None) -> str:
    return status.value if status is not None else "None"


def _candidate_for(kind: ActivityKind) -> ReactionCandidate | None:
    if kind is ActivityKind.VOICE_JOINED:
        return ReactionCandidate(
            kind=EventReactionKind.GREETING,
            text=_VOICE_JOINED_TEXT,
            reason="actor joined voice channel",
            priority=10,
        )
    if kind is ActivityKind.APP_OPENED:
        return ReactionCandidate(
            kind=EventReactionKind.GREETING,
            text=_APP_OPENED_TEXT,
            reason="actor opened app",
            priority=5,
        )
    return None
