"""認知パイプライン向けの WorkspaceFrame と関連スナップショット型。"""

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
    """観測から抽出された、解釈済みテキスト入力。"""

    text: str | None = None
    language: str | None = None
    intent_hint: str | None = None


@dataclass(frozen=True)
class MemorySummary:
    """現在のターンで取得したメモリ。"""

    retrieved_memories: tuple[MemorySearchResult, ...] = ()


@dataclass(frozen=True)
class AffectSnapshot:
    """現在の感情状態。"""

    mood_label: str | None = None
    arousal: float = 0.0
    valence: float = 0.0
    dominance: float = 0.0
    affect_summary: str | None = None


@dataclass(frozen=True)
class RelationshipSnapshot:
    """現在のアクターとの関係状態。"""

    actor_label: str | None = None
    affinity: float = 0.0
    trust: float = 0.0
    familiarity: float = 0.0
    relationship_summary: str | None = None


@dataclass(frozen=True)
class GoalCandidate:
    """認知サイクルが考慮する候補ゴール。"""

    name: str
    reason: str
    priority: int


@dataclass(frozen=True)
class ActorContextSnapshot:
    """1 ターンで参照可能なアクター・アカウント・デバイスコンテキスト。"""

    actor: Identity | None = None
    account_id: AccountId | None = None
    device_id: DeviceId | None = None


@dataclass(frozen=True)
class SpaceContextSnapshot:
    """1 ターンで参照可能なスペースコンテキスト。"""

    space_id: SpaceId | None = None
    space: InteractionSpace | None = None
    participant_actor_ids: tuple[ActorId, ...] = ()


@dataclass(frozen=True)
class WorkspaceFrame:
    """1 ターン分の、型付きで不変なワーキングメモリスナップショット。"""

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
