"""プロアクティブ発話機能のプロトコルとデータモデル。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from iris.contracts.memory import MemorySearchResult
    from iris.contracts.observations import Observation
    from iris.contracts.policy import ActionPreference, PolicyConstraint


class ProactiveMemoryContext(Protocol):
    """プロアクティブスコアリングにメモリコンテキストを提供するプロトコル。"""

    retrieved_memories: tuple[MemorySearchResult, ...]


class ProactiveAffectContext(Protocol):
    """プロアクティブスコアリングに感情コンテキストを提供するプロトコル。"""

    arousal: float
    valence: float


class ProactiveRelationshipContext(Protocol):
    """プロアクティブスコアリングに関係コンテキストを提供するプロトコル。"""

    user_label: str | None
    familiarity: float


class ProactiveFrameContext(Protocol):
    """プロアクティブ発話パイプラインステップの完全なフレームプロトコル。"""

    observation: Observation
    memory_summary: ProactiveMemoryContext
    affect: ProactiveAffectContext
    relationship: ProactiveRelationshipContext
    constraints: tuple[PolicyConstraint, ...]
    action_preferences: tuple[ActionPreference, ...]


@dataclass(frozen=True)
class ProactiveSalience:
    """Irisが会話を開始すべきかを示す顕著性スコア。"""

    score: float
    threshold: float
    reasons: tuple[str, ...] = ()
    blocked: bool = False

    @property
    def should_speak(self) -> bool:
        """スコアが閾値以上かつブロックされていない場合にTrue。"""
        return not self.blocked and self.score >= self.threshold


@dataclass(frozen=True)
class ProactiveGoal:
    """顕著性スコアリングから導出されたゴール。"""

    name: str
    reason: str
    should_speak: bool
    priority: int = 0
