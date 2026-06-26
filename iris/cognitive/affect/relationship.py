"""アクター関係追跡のための関係状態とパイプラインステップ。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, override

from iris.cognitive.affect.common import clamp_value
from iris.cognitive.cycle.models import RelationshipResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.cognitive.workspace.frame import AffectSnapshot, RelationshipSnapshot, WorkspaceFrame
from iris.contracts.relationship import RelationshipSnapshotRecord, RelationshipStore

if TYPE_CHECKING:
    from iris.core.ids import ActorId, ObservationId

_POSITIVE_VALENCE_TRUST_THRESHOLD = 0.1
_NEGATIVE_VALENCE_TRUST_THRESHOLD = -0.1
_WARM_AFFINITY_THRESHOLD = 0.4
_STRAINED_AFFINITY_THRESHOLD = -0.4


class RelationshipStep(PipelineStep[RelationshipResult]):
    """ActorId ごとの関係性 state を更新して永続 store に保存するステップ。"""

    name = "relationship"

    def __init__(self, store: RelationshipStore) -> None:
        """関係性 state store を受け取る。"""
        self._store = store

    @override
    async def run(self, frame: WorkspaceFrame) -> RelationshipResult:
        """現在の actor と affect から関係性 state を更新する。

        Returns:
            更新された関係性を表す RelationshipResult。
        """
        actor = frame.actor_context.actor
        if actor is None:
            return RelationshipResult(
                step_name=self.name,
                status=StepStatus.SKIPPED,
                reason="missing_actor",
            )

        current_record = await asyncio.to_thread(self._store.get, actor.actor_id)
        current_snapshot = (
            _record_to_snapshot(current_record)
            if current_record is not None
            else default_relationship_snapshot(actor.display_name)
        )
        updated_snapshot = update_relationship(current_snapshot, frame.affect)
        record = _record_from_snapshot(
            actor_id=actor.actor_id,
            snapshot=updated_snapshot,
            source_observation_id=frame.observation.observation_id,
        )
        stored = await asyncio.to_thread(self._store.upsert, record)
        return _result_from_record(stored)


def default_relationship_snapshot(actor_label: str | None) -> RelationshipSnapshot:
    """新規 actor 用のデフォルト関係性スナップショットを返す。

    Returns:
        初期値を持つ RelationshipSnapshot。
    """
    return RelationshipSnapshot(
        actor_label=actor_label,
        affinity=0.0,
        trust=0.5,
        familiarity=0.0,
        relationship_summary=_summarize(actor_label, 0.0, 0.5, 0.0),
    )


def update_relationship(
    current: RelationshipSnapshot,
    affect: AffectSnapshot,
) -> RelationshipSnapshot:
    """現在の affect を保守的に反映した新しい関係性 state を返す。

    Returns:
        更新後の RelationshipSnapshot。
    """
    affinity_delta = affect.valence * 0.05
    trust_delta = 0.0
    if affect.valence > _POSITIVE_VALENCE_TRUST_THRESHOLD:
        trust_delta = 0.02
    elif affect.valence < _NEGATIVE_VALENCE_TRUST_THRESHOLD:
        trust_delta = -0.02

    familiarity = clamp_value(current.familiarity + 0.05, lower=0.0, upper=1.0)
    affinity = clamp_value(current.affinity + affinity_delta, lower=-1.0, upper=1.0)
    trust = clamp_value(current.trust + trust_delta, lower=0.0, upper=1.0)
    return RelationshipSnapshot(
        actor_label=current.actor_label,
        affinity=affinity,
        trust=trust,
        familiarity=familiarity,
        relationship_summary=_summarize(
            current.actor_label,
            affinity,
            trust,
            familiarity,
        ),
    )


def _record_to_snapshot(record: RelationshipSnapshotRecord) -> RelationshipSnapshot:
    """永続化 record を workspace 用 snapshot に変換する。

    Returns:
        WorkspaceFrame 用 RelationshipSnapshot。
    """
    return RelationshipSnapshot(
        actor_label=record.actor_label,
        affinity=record.affinity,
        trust=record.trust,
        familiarity=record.familiarity,
        relationship_summary=record.relationship_summary,
    )


def _record_from_snapshot(
    *,
    actor_id: ActorId,
    snapshot: RelationshipSnapshot,
    source_observation_id: ObservationId,
) -> RelationshipSnapshotRecord:
    """Workspace snapshot を永続化 record に変換する。

    Returns:
        RelationshipStore に保存する RelationshipSnapshotRecord。
    """
    return RelationshipSnapshotRecord(
        actor_id=actor_id,
        actor_label=snapshot.actor_label,
        affinity=snapshot.affinity,
        trust=snapshot.trust,
        familiarity=snapshot.familiarity,
        relationship_summary=snapshot.relationship_summary,
        source_observation_id=source_observation_id,
    )


def _result_from_record(record: RelationshipSnapshotRecord) -> RelationshipResult:
    """保存済み record から RelationshipResult を作る。

    Returns:
        PipelineStepResult として返す RelationshipResult。
    """
    return RelationshipResult(
        step_name=RelationshipStep.name,
        status=StepStatus.OK,
        actor_label=record.actor_label,
        affinity=record.affinity,
        trust=record.trust,
        familiarity=record.familiarity,
        relationship_summary=record.relationship_summary,
    )


def _summarize(
    actor_label: str | None,
    affinity: float,
    trust: float,
    familiarity: float,
) -> str:
    """関係性 state の短い説明文を作る。

    Returns:
        関係性 state の短い説明文。
    """
    label = actor_label or "actor"
    if affinity > _WARM_AFFINITY_THRESHOLD:
        tone = "warm"
    elif affinity < _STRAINED_AFFINITY_THRESHOLD:
        tone = "strained"
    else:
        tone = "neutral"
    return f"{label}: {tone} relationship, trust={trust:.2f}, familiarity={familiarity:.2f}"
