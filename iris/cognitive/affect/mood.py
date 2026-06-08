"""ニュートラルへの指数減衰を伴うムード更新関数。"""

from __future__ import annotations

import math

from iris.cognitive.affect.common import clamp_value, format_vad_summary, label_for_vad
from iris.cognitive.workspace.frame import AffectSnapshot

_HALF_LIFE_SECONDS = 600.0


def update_mood(
    current: AffectSnapshot,
    appraisal: AffectSnapshot,
    *,
    elapsed_seconds: float,
    half_life_seconds: float = _HALF_LIFE_SECONDS,
) -> AffectSnapshot:
    """現在の状態と新しいアプレイザルをブレンドし、減衰を適用してムードを更新する。

    Returns:
        AffectSnapshot: 減衰と新しい評価を反映した更新後の感情スナップショット。
    """
    decay = _decay_factor(elapsed_seconds, half_life_seconds)
    valence = clamp_value(current.valence * decay + appraisal.valence * (1.0 - decay + 0.35))
    arousal = clamp_value(current.arousal * decay + appraisal.arousal * (1.0 - decay + 0.35))
    dominance = clamp_value(current.dominance * decay + appraisal.dominance * (1.0 - decay + 0.35))
    mood_label = appraisal.mood_label or label_for_vad(valence, arousal, dominance)
    return AffectSnapshot(
        mood_label=mood_label,
        arousal=arousal,
        valence=valence,
        dominance=dominance,
        affect_summary=format_vad_summary(mood_label, valence, arousal, dominance),
    )


def _decay_factor(elapsed_seconds: float, half_life_seconds: float) -> float:
    if elapsed_seconds <= 0.0:
        return 1.0
    if half_life_seconds <= 0.0:
        return 0.0
    return math.pow(0.5, elapsed_seconds / half_life_seconds)
