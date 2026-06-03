from __future__ import annotations

from dataclasses import replace

from iris.cognitive.cycle.models import (
    ActionSelectionResult,
    AppraisalResult,
    MemoryRetrievalResult,
    MotivationResult,
    PerceptionResult,
    PipelineStepResult,
    PolicyResult,
    RelationshipResult,
)
from iris.cognitive.workspace.frame import (
    AffectSnapshot,
    GoalCandidate,
    InterpretedInput,
    MemorySummary,
    RelationshipSnapshot,
    WorkspaceFrame,
)


class FrameBuilder:
    def apply(self, frame: WorkspaceFrame, result: PipelineStepResult) -> WorkspaceFrame:
        match result:
            case PerceptionResult():
                return replace(
                    frame,
                    interpreted_input=InterpretedInput(
                        text=result.text,
                        language=result.language,
                        intent_hint=result.intent_hint,
                    ),
                )
            case MemoryRetrievalResult():
                return replace(
                    frame,
                    memory_summary=MemorySummary(retrieved_memories=result.memories),
                )
            case AppraisalResult():
                return replace(
                    frame,
                    affect=AffectSnapshot(
                        mood_label=result.mood_label,
                        arousal=result.arousal,
                        valence=result.valence,
                        dominance=result.dominance,
                        affect_summary=result.affect_summary,
                    ),
                )
            case RelationshipResult():
                return replace(
                    frame,
                    relationship=RelationshipSnapshot(
                        user_label=result.user_label,
                        affinity=result.affinity,
                        trust=result.trust,
                        familiarity=result.familiarity,
                        relationship_summary=result.relationship_summary,
                    ),
                )
            case MotivationResult():
                return replace(
                    frame,
                    goals=tuple(
                        GoalCandidate(name=goal, reason="pipeline", priority=index)
                        for index, goal in enumerate(result.goals)
                    ),
                )
            case PolicyResult():
                return replace(
                    frame,
                    constraints=result.constraints,
                    action_preferences=result.action_preferences,
                    policy_summary=result.policy_summary,
                )
            case ActionSelectionResult():
                return replace(frame, candidate_action_plans=result.action_plans)
            case _:
                raise TypeError(f"Unsupported step result: {type(result).__name__}")
