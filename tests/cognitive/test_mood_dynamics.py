"""気分動態の減衰と更新ロジックのテスト。"""

from __future__ import annotations

import pytest

from iris.cognitive.affect.mood import update_mood
from iris.cognitive.workspace.frame import AffectSnapshot


def test_mood_decays_toward_neutral_deterministically() -> None:
    """気分が600秒間で中立に向かって半分に減衰することを確認する。"""
    current = AffectSnapshot(mood_label="positive", valence=0.8, arousal=0.4, dominance=0.2)
    neutral = AffectSnapshot()

    mood = update_mood(current, neutral, elapsed_seconds=600.0)

    assert mood.valence == pytest.approx(0.4)
    assert mood.arousal == pytest.approx(0.2)
    assert mood.dominance == pytest.approx(0.1)


def test_mood_updates_from_current_appraisal() -> None:
    """elapsed=0で新しいアプレイザルから気分が即座に更新されることを確認する。"""
    mood = update_mood(
        AffectSnapshot(),
        AffectSnapshot(mood_label="negative", valence=-0.5, arousal=0.2, dominance=-0.25),
        elapsed_seconds=0.0,
    )

    assert mood.mood_label == "negative"
    assert mood.valence == pytest.approx(-0.175)
    assert mood.arousal == pytest.approx(0.06999999999999999)
    assert mood.dominance == pytest.approx(-0.0875)
