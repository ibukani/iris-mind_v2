"""FrameBuilder はパイプラインステップの結果を WorkspaceFrame に適用する。"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from iris.cognitive.cycle.models import (
    ActionSelectionResult,
    AppraisalResult,
    MemoryRetrievalResult,
    MemoryWriteResult,
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
    def _apply_perception(frame: WorkspaceFrame, result: PerceptionResult) -> WorkspaceFrame:
        return replace(
            frame,
            interpreted_input=InterpretedInput(
                text=result.text,
                language=result.language,
                intent_hint=result.intent_hint,
            ),
        )

    @staticmethod
    def _apply_memory_retrieval(
        frame: WorkspaceFrame,
        result: MemoryRetrievalResult,
    ) -> WorkspaceFrame:
        return replace(
            frame,
            memory_summary=MemorySummary(retrieved_memories=result.memories),
        )

    @staticmethod
    def _apply_appraisal(frame: WorkspaceFrame, result: AppraisalResult) -> WorkspaceFrame:
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

    @staticmethod
    def _apply_relationship(frame: WorkspaceFrame, result: RelationshipResult) -> WorkspaceFrame:
        return replace(
            frame,
            relationship=RelationshipSnapshot(
                actor_label=result.actor_label,
                affinity=result.affinity,
                trust=result.trust,
                familiarity=result.familiarity,
                relationship_summary=result.relationship_summary,
            ),
        )

    @staticmethod
    def _apply_motivation(frame: WorkspaceFrame, result: MotivationResult) -> WorkspaceFrame:
        return replace(
            frame,
            goals=tuple(
                GoalCandidate(name=goal, reason="pipeline", priority=index)
                for index, goal in enumerate(result.goals)
            ),
        )

    @staticmethod
    def _apply_policy(frame: WorkspaceFrame, result: PolicyResult) -> WorkspaceFrame:
        return replace(
            frame,
            constraints=result.constraints,
            action_preferences=result.action_preferences,
            policy_summary=result.policy_summary,
        )

    @staticmethod
    def _apply_action_selection(
        frame: WorkspaceFrame,
        result: ActionSelectionResult,
    ) -> WorkspaceFrame:
        return replace(frame, candidate_action_plans=result.action_plans)

    @staticmethod
    def _dispatch(frame: WorkspaceFrame, result: PipelineStepResult) -> WorkspaceFrame:
        updated: WorkspaceFrame | None = None
        if isinstance(result, PerceptionResult):
            updated = FrameBuilder._apply_perception(frame, result)
        elif isinstance(result, MemoryRetrievalResult):
            updated = FrameBuilder._apply_memory_retrieval(frame, result)
        elif isinstance(result, AppraisalResult):
            updated = FrameBuilder._apply_appraisal(frame, result)
        elif isinstance(result, RelationshipResult):
            updated = FrameBuilder._apply_relationship(frame, result)
        elif isinstance(result, MotivationResult):
            updated = FrameBuilder._apply_motivation(frame, result)
        elif isinstance(result, PolicyResult):
            updated = FrameBuilder._apply_policy(frame, result)
        elif isinstance(result, ActionSelectionResult):
            updated = FrameBuilder._apply_action_selection(frame, result)
        else:
            msg = f"Unsupported pipeline step result: {type(result).__name__}"
            raise TypeError(msg)
        return updated

    @staticmethod
    def apply(frame: WorkspaceFrame, result: PipelineStepResult) -> WorkspaceFrame:
        """型付きパイプライン結果をフレームに適用する。

        Returns:
            更新されたワークスペースフレーム。
        """
        if isinstance(result, MemoryWriteResult):
            return frame
        return FrameBuilder._dispatch(frame, result)
