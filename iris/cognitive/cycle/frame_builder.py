"""FrameBuilder はパイプラインステップの結果を WorkspaceFrame に適用する。"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from iris.cognitive.cycle.models import (
    ActionSelectionResult,
    AffectBaselineLoadResult,
    AffectPersistenceResult,
    AppraisalResult,
    MemoryRetrievalResult,
    MemoryWriteResult,
    MotivationResult,
    PerceptionResult,
    PipelineStepResult,
    PolicyResult,
    RelationshipResult,
    StepStatus,
)
from iris.cognitive.workspace.frame import (
    ActorContextSnapshot,
    AffectSnapshot,
    GoalCandidate,
    InterpretedInput,
    MemorySummary,
    RelationshipSnapshot,
    SituationContextSnapshot,
    SpaceContextSnapshot,
    WorkspaceFrame,
)

if TYPE_CHECKING:
    from iris.contracts.observations import Observation


class FrameBuilder:
    """型付きパイプライン結果を不変 WorkspaceFrame スナップショットへ適用する。"""

    @staticmethod
    def build_initial(
        observation: Observation,
        *,
        situation_context: SituationContextSnapshot | None = None,
    ) -> WorkspaceFrame:
        """観測コンテキストから初期フレームを構築する。

        Args:
            observation: 入ってきた観測。
            situation_context: ランタイムから組み立てられた任意の状況コンテキスト。

        Returns:
            actor / space / situation context スナップショットを含む初期ワークスペースフレーム。
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
            situation_context=situation_context or SituationContextSnapshot(),
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
    def _apply_affect_baseline_load(
        frame: WorkspaceFrame,
        result: AffectBaselineLoadResult,
    ) -> WorkspaceFrame:
        if result.status is not StepStatus.OK:
            return frame
        return replace(
            frame,
            affect=AffectSnapshot(
                mood_label=result.mood_label,
                valence=result.valence,
                arousal=result.arousal,
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
        match result:
            case PerceptionResult():
                updated = FrameBuilder._apply_perception(frame, result)
            case MemoryRetrievalResult():
                updated = FrameBuilder._apply_memory_retrieval(frame, result)
            case AppraisalResult():
                updated = FrameBuilder._apply_appraisal(frame, result)
            case RelationshipResult():
                updated = FrameBuilder._apply_relationship(frame, result)
            case MotivationResult():
                updated = FrameBuilder._apply_motivation(frame, result)
            case PolicyResult():
                updated = FrameBuilder._apply_policy(frame, result)
            case ActionSelectionResult():
                updated = FrameBuilder._apply_action_selection(frame, result)
            case _:
                msg = f"Unsupported pipeline step result: {type(result).__name__}"
                raise TypeError(msg)
        return updated

    @staticmethod
    def apply(frame: WorkspaceFrame, result: PipelineStepResult) -> WorkspaceFrame:
        """型付きパイプライン結果をフレームに適用する。

        Returns:
            更新されたワークスペースフレーム。
        """
        match result:
            case AffectBaselineLoadResult():
                return FrameBuilder._apply_affect_baseline_load(frame, result)
            case AffectPersistenceResult() | MemoryWriteResult():
                return frame
            case _:
                return FrameBuilder._dispatch(frame, result)
