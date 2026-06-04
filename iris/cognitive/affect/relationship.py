"""アクター関係追跡のための関係状態とパイプラインステップ。"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, override

from iris.cognitive.cycle.models import RelationshipResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.cognitive.workspace.frame import AffectSnapshot, RelationshipSnapshot, WorkspaceFrame

if TYPE_CHECKING:
    from iris.core.ids import ActorId

_POSITIVE_VALENCE_TRUST_THRESHOLD = 0.1
_NEGATIVE_VALENCE_TRUST_THRESHOLD = -0.1


class InMemoryRelationshipState:
    """アクターIDをキーとする関係スナップショットのインメモリ保存。"""

    def __init__(self) -> None:
        """空の関係状態ストアを初期化する。"""
        self._snapshots: dict[ActorId, RelationshipSnapshot] = {}

    def get(self, actor_id: ActorId, actor_label: str | None = None) -> RelationshipSnapshot:
        """アクターの関係スナップショットを取得する。存在しない場合はデフォルト値を返す。

        Returns:
            RelationshipSnapshot: アクターの関係スナップショット。存在しない場合はデフォルト値。
        """
        snapshot = self._snapshots.get(actor_id)
        if snapshot is not None:
            return snapshot
        return RelationshipSnapshot(
            actor_label=actor_label,
            affinity=0.0,
            trust=0.5,
            familiarity=0.0,
            relationship_summary=_summarize(actor_label, 0.0, 0.5, 0.0),
        )

    def set(self, actor_id: ActorId, snapshot: RelationshipSnapshot) -> None:
        """アクターの関係スナップショットを保存する。"""
        self._snapshots[actor_id] = snapshot


class RelationshipStep(PipelineStep[RelationshipResult]):
    """感情に基づいて関係状態を更新するパイプラインステップ。"""

    name = "relationship"

    def __init__(self, state: InMemoryRelationshipState | None = None) -> None:
        """オプションの関係状態ストアで初期化する。

        Args:
            state: The relationship state store. Defaults to InMemoryRelationshipState().
        """
        self._state = state if state is not None else InMemoryRelationshipState()

    @override
    async def run(self, frame: WorkspaceFrame) -> RelationshipResult:
        """フレームのアクターに対する関係を更新し、結果を返す。

        Returns:
            RelationshipResult: 更新された関係情報。actor がない場合は SKIPPED。
        """
        actor = frame.observation.actor
        if actor is None:
            return RelationshipResult(
                step_name=self.name,
                status=StepStatus.SKIPPED,
                reason="no actor identity",
            )

        snapshot = self._state.get(actor.actor_id, actor.display_name)
        updated = update_relationship(snapshot, frame.affect)
        self._state.set(actor.actor_id, updated)
        return RelationshipResult(
            step_name=self.name,
            status=StepStatus.OK,
            actor_label=updated.actor_label,
            affinity=updated.affinity,
            trust=updated.trust,
            familiarity=updated.familiarity,
            relationship_summary=updated.relationship_summary,
        )


def update_relationship(
    current: RelationshipSnapshot,
    affect: AffectSnapshot,
) -> RelationshipSnapshot:
    """現在の感情状態に基づいて関係スナップショットを更新する。

    Returns:
        RelationshipSnapshot: 親密度、親和性、信頼度が更新された関係スナップショット。
    """
    familiarity = _clamp01(current.familiarity + 0.02)
    affinity = _clamp_signed(current.affinity + affect.valence * 0.04)
    if affect.valence > _POSITIVE_VALENCE_TRUST_THRESHOLD:
        trust_delta = 0.015
    elif affect.valence < _NEGATIVE_VALENCE_TRUST_THRESHOLD:
        trust_delta = -0.01
    else:
        trust_delta = 0.0
    trust = _clamp01(current.trust + trust_delta)
    return replace(
        current,
        familiarity=familiarity,
        affinity=affinity,
        trust=trust,
        relationship_summary=_summarize(current.actor_label, affinity, trust, familiarity),
    )


def _summarize(actor_label: str | None, affinity: float, trust: float, familiarity: float) -> str:
    label = actor_label or "unknown actor"
    return (
        f"{label} relationship(affinity={affinity:.2f}, trust={trust:.2f}, "
        f"familiarity={familiarity:.2f})"
    )


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _clamp_signed(value: float) -> float:
    return max(-1.0, min(1.0, value))
