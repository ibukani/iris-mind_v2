"""認知パイプラインの型付きステップ結果とサイクルモデル。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import WorkspaceFrame
    from iris.contracts.actions import ActionPlan
    from iris.contracts.memory import MemorySearchResult
    from iris.contracts.policy import ActionPreference, PolicyConstraint


class StepStatus(StrEnum):
    """パイプラインステップ実行のステータス。"""

    OK = "ok"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True)
class PipelineStepResult:
    """パイプラインステップの基本結果。"""

    step_name: str
    status: StepStatus
    reason: str | None = None


@dataclass(frozen=True)
class PerceptionResult(PipelineStepResult):
    """知覚ステップの結果。"""

    text: str | None = None
    language: str | None = None
    intent_hint: str | None = None


@dataclass(frozen=True)
class MemoryRetrievalResult(PipelineStepResult):
    """メモリ検索ステップの結果。"""

    memories: tuple[MemorySearchResult, ...] = ()


@dataclass(frozen=True)
class AppraisalResult(PipelineStepResult):
    """感情アプレイザルステップの結果。"""

    mood_label: str | None = None
    arousal: float = 0.0
    valence: float = 0.0
    dominance: float = 0.0
    affect_summary: str | None = None


@dataclass(frozen=True)
class RelationshipResult(PipelineStepResult):
    """関係ステップの結果。"""

    actor_label: str | None = None
    affinity: float = 0.0
    trust: float = 0.0
    familiarity: float = 0.0
    relationship_summary: str | None = None


@dataclass(frozen=True)
class MotivationResult(PipelineStepResult):
    """動機付けステップの結果。"""

    goals: tuple[str, ...] = ()


@dataclass(frozen=True)
class PolicyResult(PipelineStepResult):
    """ポリシーステップの結果。"""

    constraints: tuple[PolicyConstraint, ...] = ()
    action_preferences: tuple[ActionPreference, ...] = ()
    response_allowed: bool = True
    policy_summary: str | None = None


@dataclass(frozen=True)
class ActionSelectionResult(PipelineStepResult):
    """アクション選択ステップの結果。"""

    action_plans: tuple[ActionPlan, ...] = ()


@dataclass(frozen=True)
class CycleResult:
    """認知サイクル実行の最終結果。"""

    frame: WorkspaceFrame
    selected_plan: ActionPlan
