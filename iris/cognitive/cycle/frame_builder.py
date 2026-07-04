"""FrameBuilder はパイプラインステップの結果を WorkspaceFrame に適用する。"""

from __future__ import annotations

from dataclasses import dataclass, replace
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
    SafetyContextResult,
    StepStatus,
)
from iris.cognitive.workspace.frame import (
    AffectSnapshot,
    AppraisalSemanticsSnapshot,
    GoalCandidate,
    InterpretedInput,
    MemorySummary,
    RelationshipSnapshot,
    WorkspaceFrame,
)
from iris.contracts.workspace_context import (
    ActorContextSnapshot,
    SituationContextSnapshot,
    SpaceContextSnapshot,
)

if TYPE_CHECKING:
    from iris.contracts.actions import ActionPlan
    from iris.contracts.observations import Observation
    from iris.contracts.policy import ActionPreference, PolicyConstraint
    from iris.contracts.safety import SafetyContext


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
            conversation_history=(
                situation_context.conversation_window.records
                if situation_context is not None
                else ()
            ),
            conversation_summary=(
                situation_context.conversation_window.summary
                if situation_context is not None
                else None
            ),
        )

    @staticmethod
    def _apply_perception(frame: WorkspaceFrame, result: PerceptionResult) -> WorkspaceFrame:
        updates = replace(
            _current_updates(frame),
            interpreted_input=InterpretedInput(
                text=result.text,
                language=result.language,
                intent_hint=result.intent_hint,
            ),
        )
        return _rebuild_frame(frame, updates)

    @staticmethod
    def _apply_memory_retrieval(
        frame: WorkspaceFrame,
        result: MemoryRetrievalResult,
    ) -> WorkspaceFrame:
        updates = replace(
            _current_updates(frame),
            memory_summary=MemorySummary(retrieved_memories=result.memories),
        )
        return _rebuild_frame(frame, updates)

    @staticmethod
    def _apply_appraisal(frame: WorkspaceFrame, result: AppraisalResult) -> WorkspaceFrame:
        updates = replace(
            _current_updates(frame),
            affect=AffectSnapshot(
                mood_label=result.mood_label,
                arousal=result.arousal,
                valence=result.valence,
                dominance=result.dominance,
                affect_summary=result.affect_summary,
            ),
            appraisal=AppraisalSemanticsSnapshot(
                signals=result.appraisal_signals,
                summary=result.appraisal_summary,
            ),
        )
        return _rebuild_frame(frame, updates)

    @staticmethod
    def _apply_affect_baseline_load(
        frame: WorkspaceFrame,
        result: AffectBaselineLoadResult,
    ) -> WorkspaceFrame:
        if result.status is not StepStatus.OK:
            return frame
        updates = replace(
            _current_updates(frame),
            affect=AffectSnapshot(
                mood_label=result.mood_label,
                valence=result.valence,
                arousal=result.arousal,
                dominance=result.dominance,
                affect_summary=result.affect_summary,
            ),
        )
        return _rebuild_frame(frame, updates)

    @staticmethod
    def _apply_relationship(frame: WorkspaceFrame, result: RelationshipResult) -> WorkspaceFrame:
        updates = replace(
            _current_updates(frame),
            relationship=RelationshipSnapshot(
                actor_label=result.actor_label,
                affinity=result.affinity,
                trust=result.trust,
                familiarity=result.familiarity,
                relationship_summary=result.relationship_summary,
            ),
        )
        return _rebuild_frame(frame, updates)

    @staticmethod
    def _apply_motivation(frame: WorkspaceFrame, result: MotivationResult) -> WorkspaceFrame:
        updates = replace(
            _current_updates(frame),
            goals=tuple(
                GoalCandidate(name=goal, reason="pipeline", priority=index)
                for index, goal in enumerate(result.goals)
            ),
        )
        return _rebuild_frame(frame, updates)

    @staticmethod
    def _apply_safety_context(
        frame: WorkspaceFrame,
        result: SafetyContextResult,
    ) -> WorkspaceFrame:
        updates = replace(
            _current_updates(frame),
            safety_contexts=result.safety_contexts,
        )
        return _rebuild_frame(frame, updates)

    @staticmethod
    def _apply_policy(frame: WorkspaceFrame, result: PolicyResult) -> WorkspaceFrame:
        updates = replace(
            _current_updates(frame),
            constraints=result.constraints,
            action_preferences=result.action_preferences,
            policy_summary=result.policy_summary,
        )
        return _rebuild_frame(frame, updates)

    @staticmethod
    def _apply_action_selection(
        frame: WorkspaceFrame,
        result: ActionSelectionResult,
    ) -> WorkspaceFrame:
        updates = replace(
            _current_updates(frame),
            candidate_action_plans=frame.candidate_action_plans + result.action_plans,
        )
        return _rebuild_frame(frame, updates)

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
            case SafetyContextResult():
                return FrameBuilder._apply_safety_context(frame, result)
            case AffectPersistenceResult() | MemoryWriteResult():
                return frame
            case _:
                return FrameBuilder._dispatch(frame, result)


@dataclass(frozen=True)
class _FrameUpdates:
    """FrameBuilderが適用できる型付き差分。"""

    interpreted_input: InterpretedInput | None
    memory_summary: MemorySummary
    affect: AffectSnapshot
    appraisal: AppraisalSemanticsSnapshot
    relationship: RelationshipSnapshot
    goals: tuple[GoalCandidate, ...]
    constraints: tuple[PolicyConstraint, ...]
    action_preferences: tuple[ActionPreference, ...]
    safety_contexts: tuple[SafetyContext, ...]
    candidate_action_plans: tuple[ActionPlan, ...]
    policy_summary: str | None


def _current_updates(frame: WorkspaceFrame) -> _FrameUpdates:
    return _FrameUpdates(
        interpreted_input=frame.interpreted_input,
        memory_summary=frame.memory_summary,
        affect=frame.affect,
        appraisal=frame.appraisal,
        relationship=frame.relationship,
        goals=frame.goals,
        constraints=frame.constraints,
        action_preferences=frame.action_preferences,
        safety_contexts=frame.safety_contexts,
        candidate_action_plans=frame.candidate_action_plans,
        policy_summary=frame.policy_summary,
    )


def _rebuild_frame(
    frame: WorkspaceFrame,
    updates: _FrameUpdates,
) -> WorkspaceFrame:
    """型付き差分を適用し、検証済みframeを再構築する。

    Returns:
        再検証された新しいframe。
    """
    return WorkspaceFrame(
        observation=frame.observation,
        interpreted_input=updates.interpreted_input,
        memory_summary=updates.memory_summary,
        affect=updates.affect,
        appraisal=updates.appraisal,
        relationship=updates.relationship,
        goals=updates.goals,
        constraints=updates.constraints,
        action_preferences=updates.action_preferences,
        safety_contexts=updates.safety_contexts,
        candidate_action_plans=updates.candidate_action_plans,
        policy_summary=updates.policy_summary,
        actor_context=frame.actor_context,
        space_context=frame.space_context,
        situation_context=frame.situation_context,
        conversation_history=frame.conversation_history,
        conversation_summary=frame.conversation_summary,
    )
