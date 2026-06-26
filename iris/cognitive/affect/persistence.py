"""Affect baseline persistence pipeline step。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, override

from iris.cognitive.affect.common import clamp_value
from iris.cognitive.cycle.models import AffectPersistenceResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.contracts.affect import AffectBaselineRecord, AffectStore

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import AffectSnapshot, WorkspaceFrame
    from iris.core.ids import ObservationId

_OLD_WEIGHT = 0.9
_NEW_WEIGHT = 0.1
_ZERO_AFFECT_EPSILON = 0.000001
_NO_AFFECT_MOOD_LABELS = {None, "neutral"}


class AffectPersistenceStep(PipelineStep[AffectPersistenceResult]):
    """WorkspaceFrame の affect を global baseline として保存するステップ。"""

    name = "affect_persistence"

    def __init__(self, store: AffectStore) -> None:
        """AffectStore を受け取る。"""
        self._store = store

    @override
    async def run(self, frame: WorkspaceFrame) -> AffectPersistenceResult:
        """有意な affect がある turn だけ baseline を更新する。

        Returns:
            保存有無と保存後の baseline 値を含む AffectPersistenceResult。
        """
        interpreted_input = frame.interpreted_input
        if interpreted_input is None or interpreted_input.text is None:
            return AffectPersistenceResult(
                step_name=self.name,
                status=StepStatus.SKIPPED,
                reason="missing_interpreted_input",
            )
        if not _has_meaningful_affect(frame.affect):
            return AffectPersistenceResult(
                step_name=self.name,
                status=StepStatus.SKIPPED,
                reason="no_meaningful_affect",
            )

        current = await asyncio.to_thread(self._store.get_global)
        updated = _update_baseline(
            current=current,
            affect=frame.affect,
            source_observation_id=frame.observation.observation_id,
        )
        stored = await asyncio.to_thread(self._store.upsert_global, updated)
        return AffectPersistenceResult(
            step_name=self.name,
            status=StepStatus.OK,
            persisted=True,
            mood_label=stored.mood_label,
            valence=stored.valence,
            arousal=stored.arousal,
            dominance=stored.dominance,
        )


def _has_meaningful_affect(affect: AffectSnapshot) -> bool:
    """保存対象にする affect があるかを判定する。

    Returns:
        affect baseline に反映する値がある場合は True。
    """
    return bool(
        affect.affect_summary
        or affect.mood_label not in _NO_AFFECT_MOOD_LABELS
        or abs(affect.valence) > _ZERO_AFFECT_EPSILON
        or abs(affect.arousal) > _ZERO_AFFECT_EPSILON
        or abs(affect.dominance) > _ZERO_AFFECT_EPSILON
    )


def _update_baseline(
    *,
    current: AffectBaselineRecord | None,
    affect: AffectSnapshot,
    source_observation_id: ObservationId,
) -> AffectBaselineRecord:
    """現在 affect を保守的に global baseline へ反映する。

    Returns:
        保存対象の AffectBaselineRecord。
    """
    if current is None:
        return AffectBaselineRecord(
            scope="global",
            mood_label=affect.mood_label,
            valence=affect.valence,
            arousal=affect.arousal,
            dominance=affect.dominance,
            affect_summary=affect.affect_summary,
            source_observation_id=source_observation_id,
        )
    return AffectBaselineRecord(
        scope="global",
        mood_label=affect.mood_label or current.mood_label,
        valence=_smooth(current.valence, affect.valence),
        arousal=_smooth(current.arousal, affect.arousal),
        dominance=_smooth(current.dominance, affect.dominance),
        affect_summary=affect.affect_summary or current.affect_summary,
        source_observation_id=source_observation_id,
        created_at=current.created_at,
    )


def _smooth(old_value: float, current_value: float) -> float:
    """Old * 0.9 + current * 0.1 を [-1.0, 1.0] に clamp する。

    Returns:
        clamp 済みの平滑化値。
    """
    return clamp_value(
        (old_value * _OLD_WEIGHT) + (current_value * _NEW_WEIGHT),
        lower=-1.0,
        upper=1.0,
    )
