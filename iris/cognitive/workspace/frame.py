# Copyright 2025 Iris Mind
"""WorkspaceFrame and related snapshot data types for the cognitive pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.contracts.actions import ActionPlan
    from iris.contracts.memory import MemorySearchResult
    from iris.contracts.observations import Observation
    from iris.contracts.policy import ActionPreference, PolicyConstraint


@dataclass(frozen=True)
class InterpretedInput:
    """Interpreted text input extracted from an observation."""

    text: str | None
    language: str | None
    intent_hint: str | None = None


@dataclass(frozen=True)
class MemorySummary:
    """Summary of retrieved memories for the current turn."""

    retrieved_memories: tuple[MemorySearchResult, ...] = ()


@dataclass(frozen=True)
class AffectSnapshot:
    """Snapshot of the current affect state."""

    mood_label: str | None = None
    arousal: float = 0.0
    valence: float = 0.0
    dominance: float = 0.0
    affect_summary: str | None = None


@dataclass(frozen=True)
class RelationshipSnapshot:
    """Snapshot of the relationship with the current actor."""

    actor_label: str | None = None
    affinity: float = 0.0
    trust: float = 0.0
    familiarity: float = 0.0
    relationship_summary: str | None = None


@dataclass(frozen=True)
class GoalCandidate:
    """A candidate goal produced during the cognitive cycle."""

    name: str
    reason: str
    priority: int


@dataclass(frozen=True)
class WorkspaceFrame:
    """Typed one-turn snapshot that flows through the cognitive pipeline."""

    observation: Observation
    interpreted_input: InterpretedInput | None = None
    memory_summary: MemorySummary = field(default_factory=MemorySummary)
    affect: AffectSnapshot = field(default_factory=AffectSnapshot)
    relationship: RelationshipSnapshot = field(default_factory=RelationshipSnapshot)
    goals: tuple[GoalCandidate, ...] = ()
    constraints: tuple[PolicyConstraint, ...] = ()
    action_preferences: tuple[ActionPreference, ...] = ()
    policy_summary: str | None = None
    candidate_action_plans: tuple[ActionPlan, ...] = ()
