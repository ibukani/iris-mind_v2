"""認知パイプライン向けの WorkspaceFrame と関連スナップショット型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from iris.contracts.actions import ActionPlan
from iris.contracts.memory import MemorySearchResult
from iris.contracts.observations import Observation
from iris.contracts.policy import ActionPreference, PolicyConstraint
from iris.contracts.workspace_context import (
    ActorContextSnapshot,
    SituationContextSnapshot,
    SpaceContextSnapshot,
)


class InterpretedInput(BaseModel):
    """観測から抽出された、解釈済みテキスト入力。"""

    model_config = ConfigDict(frozen=True)

    text: str | None = None
    language: str | None = None
    intent_hint: str | None = None


class MemorySummary(BaseModel):
    """現在のターンで取得したメモリ。"""

    model_config = ConfigDict(frozen=True)

    retrieved_memories: tuple[MemorySearchResult, ...] = ()


class AffectSnapshot(BaseModel):
    """現在の感情状態。"""

    model_config = ConfigDict(frozen=True)

    mood_label: str | None = None
    arousal: float = 0.0
    valence: float = 0.0
    dominance: float = 0.0
    affect_summary: str | None = None


class RelationshipSnapshot(BaseModel):
    """現在のアクターとの関係状態。"""

    model_config = ConfigDict(frozen=True)

    actor_label: str | None = None
    affinity: float = 0.0
    trust: float = 0.0
    familiarity: float = 0.0
    relationship_summary: str | None = None


class GoalCandidate(BaseModel):
    """認知サイクルが考慮する候補ゴール。"""

    model_config = ConfigDict(frozen=True)

    name: str
    reason: str
    priority: int


class WorkspaceFrame(BaseModel):
    """1 ターン分の、型付きで不変なワーキングメモリスナップショット。"""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    observation: Observation
    interpreted_input: InterpretedInput | None = None
    memory_summary: MemorySummary = Field(default_factory=MemorySummary)
    affect: AffectSnapshot = Field(default_factory=AffectSnapshot)
    relationship: RelationshipSnapshot = Field(default_factory=RelationshipSnapshot)
    goals: tuple[GoalCandidate, ...] = ()
    constraints: tuple[PolicyConstraint, ...] = ()
    action_preferences: tuple[ActionPreference, ...] = ()
    candidate_action_plans: tuple[ActionPlan, ...] = ()
    policy_summary: str | None = None
    actor_context: ActorContextSnapshot = Field(default_factory=ActorContextSnapshot)
    space_context: SpaceContextSnapshot = Field(default_factory=SpaceContextSnapshot)
    situation_context: SituationContextSnapshot = Field(
        default_factory=SituationContextSnapshot,
    )


def interpreted_input_text(frame: WorkspaceFrame) -> str | None:
    """フレームから解釈済みテキスト入力を取得する。

    Args:
        frame: 対象のワークスペースフレーム。

    Returns:
        str | None: 解釈済みテキスト入力。存在しない場合は None。
    """
    if frame.interpreted_input is None:
        return None
    return frame.interpreted_input.text


WorkspaceFrame.model_rebuild()
