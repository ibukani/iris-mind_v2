"""気分動態の減衰と更新ロジックのテスト。"""

from __future__ import annotations

from iris.cognitive.affect.mood import update_mood
from iris.cognitive.workspace.frame import AffectSnapshot
from tests.helpers.approx import approx


def test_mood_decays_toward_neutral_deterministically() -> None:
    """気分が600秒間で中立に向かって半分に減衰することを確認する。"""
    current = AffectSnapshot(mood_label="positive", valence=0.8, arousal=0.4, dominance=0.2)
    neutral = AffectSnapshot()

    mood = update_mood(current, neutral, elapsed_seconds=600.0)

    assert mood.valence == approx(0.4)
    assert mood.arousal == approx(0.2)
    assert mood.dominance == approx(0.1)


def test_mood_updates_from_current_appraisal() -> None:
    """elapsed=0で新しいアプレイザルから気分が即座に更新されることを確認する。"""
    mood = update_mood(
        AffectSnapshot(),
        AffectSnapshot(mood_label="negative", valence=-0.5, arousal=0.2, dominance=-0.25),
        elapsed_seconds=0.0,
    )

    assert mood.mood_label == "negative"
    assert mood.valence == approx(-0.175)
    assert mood.arousal == approx(0.06999999999999999)
    assert mood.dominance == approx(-0.0875)


def test_mood_label_positive() -> None:
    """Valence >= threshold のとき label が positive になる。

    elapsed_seconds=600.0 で decay=0.5 となり、ブレンド後の値 (0.3*0.85=0.255) が
    threshold (0.2) を超えるようになる。
    """
    mood = update_mood(
        AffectSnapshot(),
        AffectSnapshot(valence=0.3, arousal=0.0, dominance=0.0),
        elapsed_seconds=600.0,
    )
    assert mood.mood_label == "positive"


def test_mood_label_distressed() -> None:
    """Valence <= -threshold かつ arousal >= threshold のとき label が distressed になる。"""
    mood = update_mood(
        AffectSnapshot(),
        AffectSnapshot(valence=-0.3, arousal=0.3, dominance=0.0),
        elapsed_seconds=600.0,
    )
    assert mood.mood_label == "distressed"


def test_mood_label_negative() -> None:
    """Valence <= -threshold かつ arousal < threshold のとき label が negative になる。"""
    mood = update_mood(
        AffectSnapshot(),
        AffectSnapshot(valence=-0.3, arousal=0.0, dominance=0.0),
        elapsed_seconds=600.0,
    )
    assert mood.mood_label == "negative"


def test_mood_label_uncertain() -> None:
    """Dominance <= -threshold のとき label が uncertain になる。"""
    mood = update_mood(
        AffectSnapshot(),
        AffectSnapshot(valence=0.0, arousal=0.0, dominance=-0.3),
        elapsed_seconds=600.0,
    )
    assert mood.mood_label == "uncertain"


def test_mood_label_alert() -> None:
    """Arousal >= threshold のとき label が alert になる。"""
    mood = update_mood(
        AffectSnapshot(),
        AffectSnapshot(valence=0.0, arousal=0.3, dominance=0.0),
        elapsed_seconds=600.0,
    )
    assert mood.mood_label == "alert"


def test_mood_label_none() -> None:
    """すべてのしきい値を下回るとき label が None になる。"""
    mood = update_mood(
        AffectSnapshot(),
        AffectSnapshot(valence=0.0, arousal=0.0, dominance=0.0),
        elapsed_seconds=0.0,
    )
    assert mood.mood_label is None
