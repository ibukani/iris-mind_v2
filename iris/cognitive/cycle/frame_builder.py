"""FrameBuilder はパイプラインステップの結果を WorkspaceFrame に適用する。"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

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
    ActorContextSnapshot,
    AffectSnapshot,
    GoalCandidate,
    InterpretedInput,
    MemorySummary,
    RelationshipSnapshot,
    SpaceContextSnapshot,
    WorkspaceFrame,
)

if TYPE_CHECKING:
    from iris.contracts.observations import Observation


class FrameBuilder:
    """型付きパイプライン結果を不変 WorkspaceFrame スナップショットへ適用する。"""

    @staticmethod
    def build_initial(observation: Observation) -> WorkspaceFrame:
        """観測コンテキストから初期フレームを構築する。

        Returns:
            actor / space context スナップショットを含む初期ワークスペースフレーム。
        """
        context = observation.context
        return WorkspaceFrame(
            observation=observation,
            actor_context=ActorContextSnapshot(
                actor=context.actor,
                account_id=context.account_id,
                device_id=context.device_id,
            ),
            space_context=SpaceContextSnapshot(space_id=context.space_id),
        )

    @staticmethod
    def apply(frame: WorkspaceFrame, result: PipelineStepResult) -> WorkspaceFrame:
        """型付きパイプライン結果をフレームに適用する。

        Returns:
            更新されたワークスペースフレーム。

        Raises:
            TypeError: 未対応のパイプライン結果型。
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
                msg = f"Unsupported pipeline step result: {type(result).__name__}"
                raise TypeError(msg)

        return updated
