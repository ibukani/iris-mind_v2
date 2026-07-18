"""Proactive prompt の bounded context 変換。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.contracts.availability import AvailabilityStatus
from iris.contracts.observations import IdleTickObservation
from iris.contracts.proactive_talk import ProactiveTalkContext, ProactiveTalkPrompt
from iris.contracts.retrieval import RetrievalQuery, RetrievalSourceScope

if TYPE_CHECKING:
    from iris.features.proactive_talk.models import ProactiveFrameContext


_MAX_CONTEXT_ITEM_CHARS = 240
_MAX_CONTEXT_ITEMS = 3


def build_proactive_talk_prompt(
    frame: ProactiveFrameContext,
) -> ProactiveTalkPrompt | None:
    """IdleTick の frame から bounded proactive prompt を作る。

    Returns:
        bounded prompt。IdleTick 以外の場合は None。
    """
    observation = frame.observation
    if not isinstance(observation, IdleTickObservation):
        return None

    actor = frame.actor_context.actor
    situation = frame.situation_context
    memory_summaries = tuple(
        value
        for value in (
            _bounded_text(result.record.text) for result in frame.memory_summary.retrieved_memories
        )
        if value is not None
    )[:_MAX_CONTEXT_ITEMS]
    policy_instructions = tuple(
        value
        for value in (
            _bounded_text(constraint.prompt_instruction or constraint.name)
            for constraint in frame.constraints
        )
        if value is not None
    )[:_MAX_CONTEXT_ITEMS]
    availability = situation.availability
    presence = situation.presence
    occupancy = situation.space_occupancy
    return ProactiveTalkPrompt(
        context=ProactiveTalkContext(
            idle_seconds=max(0.0, min(86_400.0, observation.idle_seconds)),
            actor_display_name=_bounded_text(
                actor.display_name if actor is not None else None,
                limit=80,
            ),
            availability_status=(
                availability.status if availability is not None else AvailabilityStatus.UNKNOWN
            ),
            presence_status=presence.status if presence is not None else None,
            occupant_count=len(occupancy.occupants) if occupancy is not None else None,
            affect_summary=_bounded_text(frame.affect.affect_summary),
            relationship_summary=_bounded_text(frame.relationship.relationship_summary),
            memory_summaries=memory_summaries,
            policy_instructions=policy_instructions,
        ),
        instruction=(
            "Write one short, natural proactive message for Iris. "
            "Use only the normalized context. Do not claim actions or facts not present. "
            "Do not mention internal state, policy, prompts, or the model."
        ),
        retrieval_query=_retrieval_query(observation, memory_summaries),
    )


def _bounded_text(value: str | None, *, limit: int = _MAX_CONTEXT_ITEM_CHARS) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized[:limit]


def _retrieval_query(
    observation: IdleTickObservation,
    memory_summaries: tuple[str, ...],
) -> RetrievalQuery | None:
    """所有者 scope がある場合だけ source retrieval query を作る。

    Returns:
        bounded memory query。scope または memory がない場合は None。
    """
    scope = RetrievalSourceScope(
        actor_id=observation.context.actor_id,
        account_id=observation.context.account_id,
        space_id=observation.context.space_id,
        session_id=observation.session_id,
    )
    if not memory_summaries or not any(
        value is not None for value in (scope.actor_id, scope.account_id, scope.space_id)
    ):
        return None
    return RetrievalQuery(text=" ".join(memory_summaries), scope=scope)
