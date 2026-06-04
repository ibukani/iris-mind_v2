"""WorkspaceFrame and related snapshot data types for the cognitive pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.contracts.actions import ActionPlan
    from iris.contracts.identity import Identity
    from iris.contracts.memory import MemorySearchResult
    from iris.contracts.observations import Observation
    from iris.contracts.policy import ActionPreference, PolicyConstraint
    from iris.contracts.spaces import InteractionSpace
    from iris.core.ids import AccountId, ActorId, DeviceId, SpaceId


@dataclass(frozen=True)
class InterpretedInput:
    """Interpreted text input extracted from an observation."""

    text: str | None = None
    language: str | None = None
    intent_hint: str | None = None


@dataclass(frozen=True)
class MemorySummary:
    """Retrieved memories for the current turn."""

    retrieved_memories: tuple[MemorySearchResult, ...] = ()


@dataclass(frozen=True)
class AffectSnapshot:
    """Current affect state."""

    mood_label: str | None = None
    arousal: float = 0.0
    valence: float = 0.0
    dominance: float = 0.0
    affect_summary: str | None = None


@dataclass(frozen=True)
class RelationshipSnapshot:
    """Relationship state with the current actor."""

    actor_label: str | None = None
    affinity: float = 0.0
    trust: float = 0.0
    familiarity: float = 0.0
    relationship_summary: str | None = None


@dataclass(frozen=True)
class GoalCandidate:
    """Candidate goal considered by the cognitive cycle."""

    name: str
    priority: float = 0.0
    rationale: str | None = None


@dataclass(frozen=True)
class ActorContextSnapshot:
    """Actor, account, and device context available to one turn."""

    actor: Identity | None = None
    account_id: AccountId | None = None
    device_id: DeviceId | None = None


@dataclass(frozen=True)
class SpaceContextSnapshot:
    """Space context available to one turn."""

    space_id: SpaceId | None = None
    space: InteractionSpace | None = None
    participant_actor_ids: tuple[ActorId, ...] = ()


@dataclass(frozen=True)
class WorkspaceFrame:
    """Typed immutable working-memory snapshot for one cognitive turn."""

    observation: Observation
    interpreted_input: InterpretedInput | None = None
    memory_summary: MemorySummary = field(default_factory=MemorySummary)
    affect: AffectSnapshot = field(default_factory=AffectSnapshot)
    relationship: RelationshipSnapshot = field(default_factory=RelationshipSnapshot)
    goals: tuple[GoalCandidate, ...] = ()
    constraints: tuple[PolicyConstraint, ...] = ()
    action_preferences: tuple[ActionPreference, ...] = ()
    candidate_action_plans: tuple[ActionPlan, ...] = ()
    policy_summary: str | None = None
    actor_context: ActorContextSnapshot = field(default_factory=ActorContextSnapshot)
    space_context: SpaceContextSnapshot = field(default_factory=SpaceContextSnapshot)
