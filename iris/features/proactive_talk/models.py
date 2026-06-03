from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from iris.contracts.memory import MemorySearchResult
from iris.contracts.observations import Observation
from iris.contracts.policy import ActionPreference, PolicyConstraint


class ProactiveMemoryContext(Protocol):
    retrieved_memories: tuple[MemorySearchResult, ...]


class ProactiveAffectContext(Protocol):
    arousal: float
    valence: float


class ProactiveRelationshipContext(Protocol):
    user_label: str | None
    familiarity: float


class ProactiveFrameContext(Protocol):
    observation: Observation
    memory_summary: ProactiveMemoryContext
    affect: ProactiveAffectContext
    relationship: ProactiveRelationshipContext
    constraints: tuple[PolicyConstraint, ...]
    action_preferences: tuple[ActionPreference, ...]


@dataclass(frozen=True)
class ProactiveSalience:
    score: float
    threshold: float
    reasons: tuple[str, ...] = ()
    blocked: bool = False

    @property
    def should_speak(self) -> bool:
        return not self.blocked and self.score >= self.threshold


@dataclass(frozen=True)
class ProactiveGoal:
    name: str
    reason: str
    should_speak: bool
    priority: int = 0
