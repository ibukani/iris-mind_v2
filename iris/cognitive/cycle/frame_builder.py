"""FrameBuilderはパイプラインステップ結果を適用し、更新済みWorkspaceFrameを生成する。"""

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
    """構造マッチングにより型付きPipelineStepResultをWorkspaceFrameに適用する。"""

    @staticmethod
    def apply(frame: WorkspaceFrame, result: PipelineStepResult) -> WorkspaceFrame:
        """パイプラインステップ結果をフレームに適用し、更新されたコピーを返す。

        Returns:
            WorkspaceFrame: パイプラインステップの結果が適用された更新済みフレーム。

        Raises:
            TypeError: 未知の PipelineStepResult 型の場合。
        """
        match result:
            case PerceptionResult():
                updated = replace(
                    frame,
                    interpreted_input=InterpretedInput(
                        text=result.text,
                        language=result.language,
                        intent_hint=result.intent_hint,
                    ),
                )
            case MemoryRetrievalResult():
                updated = replace(
                    frame,
                    memory_summary=MemorySummary(retrieved_memories=result.memories),
                )
            case AppraisalResult():
                updated = replace(
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
                updated = replace(
                    frame,
                    relationship=RelationshipSnapshot(
                        actor_label=result.actor_label,
                        affinity=result.affinity,
                        trust=result.trust,
                        familiarity=result.familiarity,
                        relationship_summary=result.relationship_summary,
                    ),
                )
            case MotivationResult():
                updated = replace(
                    frame,
                    goals=tuple(
                        GoalCandidate(name=goal, reason="pipeline", priority=index)
                        for index, goal in enumerate(result.goals)
                    ),
                )
            case PolicyResult():
                updated = replace(
                    frame,
                    constraints=result.constraints,
                    action_preferences=result.action_preferences,
                    policy_summary=result.policy_summary,
                )
            case ActionSelectionResult():
                updated = replace(frame, candidate_action_plans=result.action_plans)
            case _:
                err = f"Unsupported step result: {type(result).__name__}"
                raise TypeError(err)
        return updated
