"""イベント反応（event reaction）の決定と内容を表す契約。"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from iris.contracts.actions import ActionPlan
from iris.contracts.activity import ActivityKind
from iris.contracts.availability import AvailabilityStatus
from iris.contracts.presence import PresenceStatus

if TYPE_CHECKING:
    from iris.contracts.observations import ActivityEventObservation
    from iris.contracts.workspace_context import SituationContextSnapshot


class EventReactionDecision(BaseModel):
    """イベント反応を行うかどうかの決定。"""

    model_config = ConfigDict(frozen=True)

    should_react: bool
    reason: str
    candidate: ActionPlan | None = None


class EventReactionOutcome(StrEnum):
    """イベント反応生成の結果種別。"""

    GENERATED = "generated"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"
    NO_SEND = "no_send"
    DEFERRED = "deferred"


class EventReactionContext(BaseModel):
    """イベント反応promptへ渡すboundedな正規化コンテキスト。"""

    model_config = ConfigDict(frozen=True)

    activity_kind: ActivityKind
    actor_display_name: str | None = Field(default=None, max_length=80)
    availability_status: AvailabilityStatus = AvailabilityStatus.UNKNOWN
    presence_status: PresenceStatus | None = None
    occupant_count: int | None = Field(default=None, ge=0)

    @classmethod
    def from_observation(
        cls,
        observation: ActivityEventObservation,
        situation_context: SituationContextSnapshot,
    ) -> EventReactionContext:
        """外部観測からraw metadataを除いたcontextを作る。

        Returns:
            EventReactionContext: promptへ渡せる正規化済みcontext。
        """
        actor = observation.context.actor
        display_name = actor.display_name.strip()[:80] if actor is not None else None
        availability = situation_context.availability
        presence = situation_context.presence
        occupancy = situation_context.space_occupancy
        return cls(
            activity_kind=observation.activity_kind,
            actor_display_name=display_name or None,
            availability_status=(
                availability.status if availability is not None else AvailabilityStatus.UNKNOWN
            ),
            presence_status=presence.status if presence is not None else None,
            occupant_count=len(occupancy.occupants) if occupancy is not None else None,
        )


class EventReactionPrompt(BaseModel):
    """イベント反応用short promptのtyped入力。"""

    model_config = ConfigDict(frozen=True)

    context: EventReactionContext
    instruction: str = Field(max_length=400)


class EventReactionGenerationResult(BaseModel):
    """イベント反応生成のtext-free診断付き結果。"""

    model_config = ConfigDict(frozen=True)

    outcome: EventReactionOutcome
    reason: str
    model: str | None = None
    text: str | None = Field(default=None, max_length=600)
