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

    @property
    def retrieved_memories(self) -> tuple[MemorySearchResult, ...]:
        """Retrieve the memories selected for the current turn."""
        ...


class ProactiveAffectContext(Protocol):
    """プロアクティブスコアリングに感情コンテキストを提供するプロトコル。"""

    @property
    def arousal(self) -> float:
        """Return the current arousal level on a bounded scale."""
        ...

    @property
    def valence(self) -> float:
        """Return the current valence level on a bounded scale."""
        ...


class ProactiveRelationshipContext(Protocol):
    """プロアクティブスコアリングに関係コンテキストを提供するプロトコル。"""

    @property
    def user_label(self) -> str | None:
        """Return the user label associated with the current session, if any."""
        ...

    @property
    def familiarity(self) -> float:
        """Return the familiarity level for the current user on a bounded scale."""
        ...


class ProactiveFrameContext(Protocol):
    """プロアクティブ発話パイプラインステップの完全なフレームプロトコル。"""

    @property
    def observation(self) -> Observation:
        """Return the current observation feeding the cognitive cycle."""
        ...

    @property
    def memory_summary(self) -> ProactiveMemoryContext:
        """Return the memory summary used for proactive scoring."""
        ...

    @property
    def affect(self) -> ProactiveAffectContext:
        """Return the affect snapshot used for proactive scoring."""
        ...

    @property
    def relationship(self) -> ProactiveRelationshipContext:
        """Return the relationship snapshot used for proactive scoring."""
        ...

    @property
    def constraints(self) -> tuple[PolicyConstraint, ...]:
        """Return the active policy constraints for the current turn."""
        ...

    @property
    def action_preferences(self) -> tuple[ActionPreference, ...]:
        """Return the action preferences emitted by upstream policy steps."""
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
