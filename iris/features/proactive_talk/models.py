"""プロアクティブ発話機能のプロトコルとデータモデル。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from iris.contracts.memory import MemorySearchResult
    from iris.contracts.observations import Observation
    from iris.contracts.policy import ActionPreference, PolicyConstraint
    from iris.contracts.workspace_context import (
        ActorContextSnapshot,
        SituationContextSnapshot,
    )


class ProactiveMemoryContext(Protocol):
    """プロアクティブスコアリングにメモリコンテキストを提供するプロトコル。"""

    @property
    def retrieved_memories(self) -> tuple[MemorySearchResult, ...]:
        """現在のターンで選択されたメモリを返す。"""
        ...


class ProactiveAffectContext(Protocol):
    """プロアクティブスコアリングに感情コンテキストを提供するプロトコル。"""

    @property
    def arousal(self) -> float:
        """現在の覚醒度を bounded スケールで返す。"""
        ...

    @property
    def valence(self) -> float:
        """現在の感情価を bounded スケールで返す。"""
        ...

    @property
    def affect_summary(self) -> str | None:
        """Prompt 用の bounded affect summary を返す。"""
        ...


class ProactiveRelationshipContext(Protocol):
    """プロアクティブスコアリングに関係コンテキストを提供するプロトコル。"""

    @property
    def actor_label(self) -> str | None:
        """現在のセッションに関連するアクターラベルを返す（存在する場合）。"""
        ...

    @property
    def familiarity(self) -> float:
        """現在のアクターに対する familiarity を bounded スケールで返す。"""
        ...

    @property
    def relationship_summary(self) -> str | None:
        """Prompt 用の bounded relationship summary を返す。"""
        ...


class ProactiveFrameContext(Protocol):
    """プロアクティブ発話パイプラインステップの完全なフレームプロトコル。"""

    @property
    def observation(self) -> Observation:
        """認知サイクルへ供給される現在の観測を返す。"""
        ...

    @property
    def actor_context(self) -> ActorContextSnapshot:
        """現在の actor identity snapshot を返す。"""
        ...

    @property
    def situation_context(self) -> SituationContextSnapshot:
        """Runtime が組み立てた bounded situation snapshot を返す。"""
        ...

    @property
    def memory_summary(self) -> ProactiveMemoryContext:
        """プロアクティブスコアリングに用いるメモリサマリーを返す。"""
        ...

    @property
    def affect(self) -> ProactiveAffectContext:
        """プロアクティブスコアリングに用いる affect スナップショットを返す。"""
        ...

    @property
    def relationship(self) -> ProactiveRelationshipContext:
        """プロアクティブスコアリングに用いる relationship スナップショットを返す。"""
        ...

    @property
    def constraints(self) -> tuple[PolicyConstraint, ...]:
        """現在のターンで有効なポリシー制約を返す。"""
        ...

    @property
    def action_preferences(self) -> tuple[ActionPreference, ...]:
        """上流のポリシーステップが出力したアクション優先度を返す。"""
        ...


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
