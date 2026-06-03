from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from iris.cognitive.workspace.frame import WorkspaceFrame
from iris.contracts.actions import ActionPlan
from iris.contracts.memory import MemorySearchResult
from iris.contracts.policy import ActionPreference, PolicyConstraint


class StepStatus(StrEnum):
    OK = "ok"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True)
class PipelineStepResult:
    step_name: str
    status: StepStatus
    reason: str | None = None


@dataclass(frozen=True)
class PerceptionResult(PipelineStepResult):
    text: str | None = None
    language: str | None = None
    intent_hint: str | None = None


@dataclass(frozen=True)
class MemoryRetrievalResult(PipelineStepResult):
    memories: tuple[MemorySearchResult, ...] = ()


@dataclass(frozen=True)
class AppraisalResult(PipelineStepResult):
    mood_label: str | None = None
    arousal: float = 0.0
    valence: float = 0.0
    dominance: float = 0.0
    affect_summary: str | None = None


@dataclass(frozen=True)
class RelationshipResult(PipelineStepResult):
    user_label: str | None = None
    affinity: float = 0.0
    trust: float = 0.0
    familiarity: float = 0.0
    relationship_summary: str | None = None


@dataclass(frozen=True)
class MotivationResult(PipelineStepResult):
    goals: tuple[str, ...] = ()


@dataclass(frozen=True)
class PolicyResult(PipelineStepResult):
    constraints: tuple[PolicyConstraint, ...] = ()
    action_preferences: tuple[ActionPreference, ...] = ()
    response_allowed: bool = True
    policy_summary: str | None = None


@dataclass(frozen=True)
class ActionSelectionResult(PipelineStepResult):
    action_plans: tuple[ActionPlan, ...] = ()


@dataclass(frozen=True)
class CycleResult:
    frame: WorkspaceFrame
    selected_plan: ActionPlan
