from __future__ import annotations

import re

from iris.cognitive.affect.mood import update_mood
from iris.cognitive.cycle.models import AppraisalResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.cognitive.workspace.frame import AffectSnapshot, WorkspaceFrame

_POSITIVE_KEYWORDS = (
    "ありがとう",
    "助かった",
    "嬉しい",
    "うれしい",
    "楽しい",
    "好き",
    "最高",
    "安心",
    "thank",
    "thanks",
    "great",
    "happy",
    "love",
)
_NEGATIVE_KEYWORDS = (
    "悲しい",
    "つらい",
    "辛い",
    "困った",
    "不安",
    "怖い",
    "嫌い",
    "最悪",
    "怒",
    "sad",
    "upset",
    "hate",
    "bad",
    "afraid",
    "scared",
)
_AROUSAL_KEYWORDS = (
    "急ぎ",
    "至急",
    "緊急",
    "今すぐ",
    "興奮",
    "楽しみ",
    "urgent",
    "asap",
    "excited",
    "hurry",
)
_LOW_DOMINANCE_KEYWORDS = (
    "わからない",
    "分からない",
    "できない",
    "無理",
    "どうしたら",
    "助けて",
    "unsure",
    "confused",
    "helpless",
    "can't",
    "cannot",
)
_TOKEN_RE = re.compile(r"[a-zA-Z']+|[^\s]+")


def classify_appraisal(text: str) -> AffectSnapshot:
    lowered = text.casefold()
    positive = _count_matches(lowered, _POSITIVE_KEYWORDS)
    negative = _count_matches(lowered, _NEGATIVE_KEYWORDS)
    arousal_hits = _count_matches(lowered, _AROUSAL_KEYWORDS)
    low_dominance_hits = _count_matches(lowered, _LOW_DOMINANCE_KEYWORDS)

    valence = _clamp((positive - negative) * 0.25)
    arousal = _clamp(arousal_hits * 0.2 + min(positive + negative, 2) * 0.05)
    dominance = _clamp(-low_dominance_hits * 0.25)
    mood_label = _label_for(valence, arousal, dominance)
    return AffectSnapshot(
        mood_label=mood_label,
        arousal=arousal,
        valence=valence,
        dominance=dominance,
        affect_summary=_summarize(mood_label, valence, arousal, dominance),
    )


class AppraisalStep(PipelineStep[AppraisalResult]):
    name = "appraisal"

    def __init__(self, *, elapsed_seconds: float = 0.0) -> None:
        self._elapsed_seconds = elapsed_seconds

    async def run(self, frame: WorkspaceFrame) -> AppraisalResult:
        if frame.interpreted_input is None or frame.interpreted_input.text is None:
            return AppraisalResult(
                step_name=self.name,
                status=StepStatus.SKIPPED,
                reason="no interpreted input text",
            )

        appraisal = classify_appraisal(frame.interpreted_input.text)
        mood = update_mood(frame.affect, appraisal, elapsed_seconds=self._elapsed_seconds)
        return AppraisalResult(
            step_name=self.name,
            status=StepStatus.OK,
            mood_label=mood.mood_label,
            arousal=mood.arousal,
            valence=mood.valence,
            dominance=mood.dominance,
            affect_summary=mood.affect_summary,
        )


def _count_matches(text: str, keywords: tuple[str, ...]) -> int:
    tokens = tuple(match.group(0).casefold() for match in _TOKEN_RE.finditer(text))
    return sum(1 for keyword in keywords if keyword.casefold() in text or keyword.casefold() in tokens)


def _label_for(valence: float, arousal: float, dominance: float) -> str | None:
    if valence >= 0.2:
        return "positive"
    if valence <= -0.2 and arousal >= 0.2:
        return "distressed"
    if valence <= -0.2:
        return "negative"
    if dominance <= -0.2:
        return "uncertain"
    if arousal >= 0.2:
        return "alert"
    return None


def _summarize(label: str | None, valence: float, arousal: float, dominance: float) -> str:
    label_part = label or "neutral"
    return f"{label_part} VAD(v={valence:.2f}, a={arousal:.2f}, d={dominance:.2f})"


def _clamp(value: float, *, lower: float = -1.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))
