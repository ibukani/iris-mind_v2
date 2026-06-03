from __future__ import annotations

from iris.cognitive.affect.mood import update_mood
from iris.cognitive.workspace.frame import AffectSnapshot


def test_mood_decays_toward_neutral_deterministically() -> None:
    current = AffectSnapshot(mood_label="positive", valence=0.8, arousal=0.4, dominance=0.2)
    neutral = AffectSnapshot()

    mood = update_mood(current, neutral, elapsed_seconds=600.0)

    assert mood.valence == 0.4
    assert mood.arousal == 0.2
    assert mood.dominance == 0.1


def test_mood_updates_from_current_appraisal() -> None:
    mood = update_mood(
        AffectSnapshot(),
        AffectSnapshot(mood_label="negative", valence=-0.5, arousal=0.2, dominance=-0.25),
        elapsed_seconds=0.0,
    )

    assert mood.mood_label == "negative"
    assert mood.valence == -0.175
    assert mood.arousal == 0.06999999999999999
    assert mood.dominance == -0.0875
