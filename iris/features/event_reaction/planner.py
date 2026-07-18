"""イベント反応候補を決定論的に導出するplanner。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.actions import ActionPlan
from iris.contracts.activity import ActivityKind
from iris.contracts.event_reaction import (
    EventReactionContext,
    EventReactionDecision,
    EventReactionPrompt,
)
from iris.contracts.retrieval import RetrievalQuery, RetrievalSourceScope

if TYPE_CHECKING:
    from iris.contracts.availability import AvailabilitySnapshot, AvailabilityStatus
    from iris.contracts.observations import ActivityEventObservation
    from iris.contracts.workspace_context import SituationContextSnapshot
    from iris.features.event_reaction.policy import EventReactionPolicy
    from iris.features.event_reaction.templates import EventReactionTemplateProvider


@dataclass(frozen=True)
class EventReactionPlanner:
    """ActivityEventObservationと状況contextから反応可否を決定する。"""

    policy: EventReactionPolicy
    template_provider: EventReactionTemplateProvider

    def plan(
        self,
        observation: ActivityEventObservation,
        *,
        availability: AvailabilitySnapshot | None,
    ) -> EventReactionDecision:
        """Activity kindとavailabilityに基づき決定論的な反応候補を返す。

        Args:
            observation: 反応対象のactivity event観測。
            availability: ランタイムが導出したavailability snapshot。

        Returns:
            EventReactionDecision: 反応するかどうかの決定と候補。
        """
        if observation.context.actor_id is None:
            return EventReactionDecision(
                should_react=False,
                reason="actor not resolved",
            )

        status = _availability_status(availability)
        if not self.policy.allows(observation.activity_kind, status):
            return EventReactionDecision(
                should_react=False,
                reason=(
                    f"{observation.activity_kind.value} not allowed "
                    f"for availability {_status_name(status)}"
                ),
            )

        candidate = _candidate_for(observation.activity_kind, self.template_provider)
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

    @staticmethod
    def build_prompt(
        observation: ActivityEventObservation,
        *,
        situation_context: SituationContextSnapshot,
    ) -> EventReactionPrompt | None:
        """既知のevent kindだけbounded prompt入力へ正規化する。

        Returns:
            EventReactionPrompt: 生成に使うprompt、未対応kindならNone。
        """
        if observation.activity_kind not in {
            ActivityKind.VOICE_JOINED,
            ActivityKind.APP_OPENED,
        }:
            return None
        return EventReactionPrompt(
            context=EventReactionContext.from_observation(observation, situation_context),
            instruction=(
                "Write one brief, warm reaction to this event. "
                "Do not claim actions or facts not present in the event context. "
                "Do not mention internal state, policy, prompt, or model."
            ),
            retrieval_query=_retrieval_query(observation),
        )


def _retrieval_query(observation: ActivityEventObservation) -> RetrievalQuery | None:
    """所有者 scope と bounded event label がある場合だけ query を作る。

    Returns:
        scope付き query。scope がない場合は None。
    """
    scope = RetrievalSourceScope(
        actor_id=observation.context.actor_id,
        account_id=observation.context.account_id,
        space_id=observation.context.space_id,
        session_id=observation.session_id,
    )
    if not any(value is not None for value in (scope.actor_id, scope.account_id, scope.space_id)):
        return None
    actor_name = observation.context.actor.display_name if observation.context.actor else None
    return RetrievalQuery(
        text=(actor_name or observation.activity_kind.value).strip(),
        scope=scope,
    )


def _availability_status(snapshot: AvailabilitySnapshot | None) -> AvailabilityStatus | None:
    return snapshot.status if snapshot is not None else None


def _status_name(status: AvailabilityStatus | None) -> str:
    return status.value if status is not None else "None"


def _candidate_for(
    kind: ActivityKind, provider: EventReactionTemplateProvider
) -> ActionPlan | None:
    text = provider.text_for_activity(kind)
    if text is None:
        return None
    if kind is ActivityKind.VOICE_JOINED:
        return ActionPlan(
            turn_intent="event_reaction",
            candidate_text=text,
            should_respond=True,
            priority=10,
        )
    if kind is ActivityKind.APP_OPENED:
        return ActionPlan(
            turn_intent="event_reaction",
            candidate_text=text,
            should_respond=True,
            priority=5,
        )
    return None
