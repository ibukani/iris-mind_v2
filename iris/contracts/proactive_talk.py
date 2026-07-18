"""Proactive text generation boundary contracts."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from iris.contracts.availability import AvailabilityStatus
from iris.contracts.presence import PresenceStatus

_MAX_CONTEXT_ITEM_CHARS = 240
_ERR_CONTEXT_ITEM_TOO_LONG = "proactive context items must be at most 240 characters"


class ProactiveGenerationOutcome(StrEnum):
    """Proactive generation の安全な結果種別。"""

    GENERATED = "generated"
    DEFERRED = "deferred"
    BLOCKED = "blocked"
    NO_SEND = "no_send"


class ProactiveTalkContext(BaseModel):
    """Prompt へ渡す bounded な proactive context。"""

    model_config = ConfigDict(frozen=True)

    idle_seconds: float = Field(ge=0.0, le=86_400.0)
    actor_display_name: str | None = Field(default=None, max_length=80)
    availability_status: AvailabilityStatus = AvailabilityStatus.UNKNOWN
    presence_status: PresenceStatus | None = None
    occupant_count: int | None = Field(default=None, ge=0, le=100)
    affect_summary: str | None = Field(default=None, max_length=240)
    relationship_summary: str | None = Field(default=None, max_length=240)
    memory_summaries: tuple[str, ...] = Field(default=(), max_length=3)
    policy_instructions: tuple[str, ...] = Field(default=(), max_length=3)

    @field_validator("memory_summaries", "policy_instructions")
    @classmethod
    def _items_must_be_bounded(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """各 context item の長さを bounded にする。

        Returns:
            検証済み context item 列。

        Raises:
            ValueError: item が最大文字数を超えた場合。
        """
        if any(len(value) > _MAX_CONTEXT_ITEM_CHARS for value in values):
            message = _ERR_CONTEXT_ITEM_TOO_LONG
            raise ValueError(message)
        return values


class ProactiveTalkPrompt(BaseModel):
    """Proactive generator に渡す typed prompt。"""

    model_config = ConfigDict(frozen=True)

    context: ProactiveTalkContext
    instruction: str = Field(min_length=1, max_length=400)


class ProactiveGenerationResult(BaseModel):
    """Proactive generation の text-free decision metadata と候補本文。"""

    model_config = ConfigDict(frozen=True)

    outcome: ProactiveGenerationOutcome
    reason: str = Field(min_length=1, max_length=200)
    model: str | None = Field(default=None, max_length=120)
    text: str | None = Field(default=None, max_length=600)
