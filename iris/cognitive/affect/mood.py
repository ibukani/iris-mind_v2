"""ニュートラルへの指数減衰を伴うムード更新関数。"""

from __future__ import annotations

import math

from iris.cognitive.workspace.frame import AffectSnapshot

_HALF_LIFE_SECONDS = 600.0
_VAD_THRESHOLD = 0.2


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
    valence = _clamp(current.valence * decay + appraisal.valence * (1.0 - decay + 0.35))
    arousal = _clamp(current.arousal * decay + appraisal.arousal * (1.0 - decay + 0.35))
    dominance = _clamp(current.dominance * decay + appraisal.dominance * (1.0 - decay + 0.35))
    mood_label = appraisal.mood_label or _label_for(valence, arousal, dominance)
    return AffectSnapshot(
        mood_label=mood_label,
        arousal=arousal,
        valence=valence,
        dominance=dominance,
        affect_summary=(
            f"{mood_label or 'neutral'} VAD(v={valence:.2f}, a={arousal:.2f}, d={dominance:.2f})"
        ),
    )


def _decay_factor(elapsed_seconds: float, half_life_seconds: float) -> float:
    if elapsed_seconds <= 0.0:
        return 1.0
    if half_life_seconds <= 0.0:
        return 0.0
    return math.pow(0.5, elapsed_seconds / half_life_seconds)


def _label_for(valence: float, arousal: float, dominance: float) -> str | None:
    if valence >= _VAD_THRESHOLD:
        return "positive"
    if valence <= -_VAD_THRESHOLD:
        return "distressed" if arousal >= _VAD_THRESHOLD else "negative"
    if dominance <= -_VAD_THRESHOLD:
        return "uncertain"
    return "alert" if arousal >= _VAD_THRESHOLD else None


def _clamp(value: float, *, lower: float = -1.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))
