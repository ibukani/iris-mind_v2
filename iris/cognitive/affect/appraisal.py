"""キーワードベースの感情アプレイザルパイプラインステップ。"""

from __future__ import annotations

from dataclasses import dataclass
from operator import itemgetter
import re
from typing import TYPE_CHECKING, override

from iris.cognitive.affect.common import clamp_value, format_vad_summary, label_for_vad
from iris.cognitive.affect.mood import update_mood
from iris.cognitive.cycle.models import AppraisalResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.cognitive.workspace.frame import AffectSnapshot, WorkspaceFrame, interpreted_input_text
from iris.contracts.appraisal import (
    AppraisalSafetyHintKind,
    AppraisalSignal,
    AppraisalSignalKind,
    AppraisalSourceSpan,
    appraisal_state_boundary_for_kind,
)
from iris.core.metadata import immutable_metadata

if TYPE_CHECKING:
    from iris.core.ids import ObservationId

_POSITIVE_KEYWORDS: tuple[str, ...] = (
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
_NEGATIVE_KEYWORDS: tuple[str, ...] = (
    "悲しい",
    "つらい",
    "辛い",
    "困った",
    "不安",
    "怖い",
    "嫌い",
    "最悪",
    "怒",
    "役に立たない",
    "使えない",
    "sad",
    "upset",
    "hate",
    "bad",
    "afraid",
    "scared",
    "useless",
)
_AROUSAL_KEYWORDS: tuple[str, ...] = (
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
_LOW_DOMINANCE_KEYWORDS: tuple[str, ...] = (
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
_GRATITUDE_KEYWORDS: tuple[str, ...] = (
    "ありがとう",
    "助かった",
    "thank",
    "thanks",
)
_IRIS_REFERENCE_KEYWORDS: tuple[str, ...] = (
    "iris",
    "イリス",
    "あなた",
    "君",
    "きみ",
    "お前",
    "you",
    "your",
)
_TOPIC_REFERENCE_KEYWORDS: tuple[str, ...] = (
    "この",
    "その",
    "映画",
    "バグ",
    "コード",
    "実装",
    "ゲーム",
    "issue",
    "bug",
    "code",
    "game",
    "movie",
    "topic",
)
_USER_EMOTION_KEYWORDS: tuple[str, ...] = (
    "悲しい",
    "つらい",
    "辛い",
    "困った",
    "不安",
    "怖い",
    "嬉しい",
    "うれしい",
    "楽しい",
    "安心",
    "sad",
    "upset",
    "afraid",
    "scared",
    "happy",
    "confused",
)
_CARE_INTENT_KEYWORDS: tuple[str, ...] = (
    "大丈夫?",
    "無理しないで",
    "休んで",
    "お大事に",
    "気をつけて",
    "take care",
    "are you okay",
    "don't overdo",
    "dont overdo",
)
_DEPENDENCY_RISK_KEYWORDS: tuple[str, ...] = (
    "いないと生きていけない",
    "いないと無理",
    "全部決めて",
    "全部 iris が決めて",
    "全部イリスが決めて",
    "君だけが頼り",
    "あなたしかいない",
    "can't live without you",
    "cannot live without you",
    "you decide everything",
)
_TOKEN_RE = re.compile(r"[a-zA-Z']+|[^\s]+")
_CLASSIFIER_METADATA = immutable_metadata({"classifier": "deterministic_appraisal_v1"})


@dataclass(frozen=True)
class _SignalCandidate:
    kind: AppraisalSignalKind
    label: str
    polarity: float
    confidence: float
    reason: str
    keywords: tuple[str, ...]
    safety_hint: AppraisalSafetyHintKind | None = None


def classify_appraisal(text: str) -> AffectSnapshot:
    """キーワードマッチングを使用してテキストの感情内容を分類する。

    Returns:
        AffectSnapshot: テキストの感情分析結果(気分ラベル, 覚醒度, valence, 支配度)。
    """
    lowered = text.casefold()
    positive = _count_matches(lowered, _POSITIVE_KEYWORDS)
    negative = _count_matches(lowered, _NEGATIVE_KEYWORDS)
    arousal_hits = _count_matches(lowered, _AROUSAL_KEYWORDS)
    low_dominance_hits = _count_matches(lowered, _LOW_DOMINANCE_KEYWORDS)

    valence = clamp_value((positive - negative) * 0.25)
    arousal = clamp_value(arousal_hits * 0.2 + min(positive + negative, 2) * 0.05)
    dominance = clamp_value(-low_dominance_hits * 0.25)
    mood_label = label_for_vad(valence, arousal, dominance)
    return AffectSnapshot(
        mood_label=mood_label,
        arousal=arousal,
        valence=valence,
        dominance=dominance,
        affect_summary=format_vad_summary(mood_label, valence, arousal, dominance),
    )


def classify_appraisal_signals(
    text: str,
    *,
    source_observation_id: ObservationId | None = None,
    dependency_risk_hint_enabled: bool = True,
) -> tuple[AppraisalSignal, ...]:
    """Companion behavior 用の typed appraisal signal を決定論的に分類する。

    Returns:
        tuple[AppraisalSignal, ...]: 分離済みの typed appraisal signal。
    """
    if not text.strip():
        return ()

    lowered = text.casefold()
    candidates = (
        _dependency_risk_candidate(lowered, enabled=dependency_risk_hint_enabled),
        _care_intent_candidate(lowered),
        _sentiment_candidate(lowered),
        _uncertain_emotion_candidate(lowered),
    )
    return tuple(
        _build_signal(text, candidate, source_observation_id)
        for candidate in candidates
        if candidate is not None
    )


def _dependency_risk_candidate(
    lowered: str,
    *,
    enabled: bool,
) -> _SignalCandidate | None:
    if not enabled or not _matches_any(lowered, _DEPENDENCY_RISK_KEYWORDS):
        return None
    return _SignalCandidate(
        kind=AppraisalSignalKind.DEPENDENCY_RISK_HINT,
        label="dependency_risk",
        polarity=-1.0,
        confidence=0.85,
        reason="dependency-risk expression matched deterministic baseline",
        keywords=_DEPENDENCY_RISK_KEYWORDS,
        safety_hint=AppraisalSafetyHintKind.DEPENDENCY_RISK,
    )


def _care_intent_candidate(lowered: str) -> _SignalCandidate | None:
    if not _matches_any(lowered, _CARE_INTENT_KEYWORDS):
        return None
    return _SignalCandidate(
        kind=AppraisalSignalKind.CARE_INTENT,
        label="care_intent",
        polarity=0.7,
        confidence=0.82,
        reason="care-intent expression matched deterministic baseline",
        keywords=_CARE_INTENT_KEYWORDS,
    )


def _sentiment_candidate(lowered: str) -> _SignalCandidate | None:
    positive_hits = _count_matches(lowered, _POSITIVE_KEYWORDS)
    negative_hits = _count_matches(lowered, _NEGATIVE_KEYWORDS)
    if positive_hits == 0 and negative_hits == 0:
        return None

    polarity = _semantic_polarity(positive_hits, negative_hits)
    attitude = _attitude_candidate(lowered, polarity)
    if attitude is not None:
        return attitude
    topic = _topic_sentiment_candidate(lowered, polarity)
    if topic is not None:
        return topic
    return _user_emotion_candidate(lowered, polarity)


def _attitude_candidate(lowered: str, polarity: float) -> _SignalCandidate | None:
    iris_referenced = _matches_any(lowered, _IRIS_REFERENCE_KEYWORDS)
    gratitude = _matches_any(lowered, _GRATITUDE_KEYWORDS)
    if not (iris_referenced or gratitude or _implicit_direct_complaint(lowered)):
        return None
    return _SignalCandidate(
        kind=AppraisalSignalKind.ATTITUDE_TOWARD_IRIS,
        label=_polarity_label("positive_attitude", "negative_attitude", polarity),
        polarity=polarity,
        confidence=0.9 if iris_referenced or gratitude else 0.72,
        reason="Iris-directed attitude matched deterministic baseline",
        keywords=_attitude_keywords(polarity),
    )


def _topic_sentiment_candidate(lowered: str, polarity: float) -> _SignalCandidate | None:
    if not _matches_any(lowered, _TOPIC_REFERENCE_KEYWORDS):
        return None
    return _SignalCandidate(
        kind=AppraisalSignalKind.TOPIC_SENTIMENT,
        label=_polarity_label("positive_topic", "negative_topic", polarity),
        polarity=polarity,
        confidence=0.78,
        reason="topic sentiment matched deterministic baseline",
        keywords=_topic_keywords(polarity),
    )


def _user_emotion_candidate(lowered: str, polarity: float) -> _SignalCandidate | None:
    if not _matches_any(lowered, _USER_EMOTION_KEYWORDS):
        return None
    return _SignalCandidate(
        kind=AppraisalSignalKind.USER_EMOTION,
        label=_polarity_label("positive_emotion", "negative_emotion", polarity),
        polarity=polarity,
        confidence=0.78,
        reason="user emotion matched deterministic baseline",
        keywords=_emotion_keywords(polarity),
    )


def _uncertain_emotion_candidate(lowered: str) -> _SignalCandidate | None:
    if _count_matches(lowered, _POSITIVE_KEYWORDS + _NEGATIVE_KEYWORDS) > 0:
        return None
    if not _matches_any(lowered, _USER_EMOTION_KEYWORDS + _LOW_DOMINANCE_KEYWORDS):
        return None
    if _matches_any(lowered, _CARE_INTENT_KEYWORDS):
        return None
    return _SignalCandidate(
        kind=AppraisalSignalKind.USER_EMOTION,
        label="uncertain_emotion",
        polarity=0.0,
        confidence=0.7,
        reason="uncertain user emotion matched deterministic baseline",
        keywords=_USER_EMOTION_KEYWORDS + _LOW_DOMINANCE_KEYWORDS,
    )


def summarize_appraisal_signals(signals: tuple[AppraisalSignal, ...]) -> str | None:
    """Signal 群を prompt/context 用の短い summary に変換する。

    Returns:
        str | None: signal が存在する場合は短い summary。
    """
    if not signals:
        return None
    return "; ".join(
        f"{signal.kind.value}:{signal.label}@{signal.confidence:.2f}" for signal in signals
    )


class AppraisalStep(PipelineStep[AppraisalResult]):
    """キーワードベースの認知アプレイザルを実行するパイプラインステップ。"""

    name = "appraisal"

    def __init__(
        self,
        *,
        elapsed_seconds: float = 0.0,
        appraisal_signals_enabled: bool = False,
        dependency_risk_hint_enabled: bool = True,
    ) -> None:
        """前回のアプレイザルからの経過時間で初期化する。

        Args:
            elapsed_seconds: 気分減衰に用いる、前回アプレイザルからの経過秒数。
            appraisal_signals_enabled: typed appraisal signals を生成するか。
            dependency_risk_hint_enabled: safety 接続用 hint を生成するか。
        """
        self._elapsed_seconds = elapsed_seconds
        self._appraisal_signals_enabled = appraisal_signals_enabled
        self._dependency_risk_hint_enabled = dependency_risk_hint_enabled

    @override
    async def run(self, frame: WorkspaceFrame) -> AppraisalResult:
        """フレームの解釈入力を評価し、アプレイザル結果を返す。

        Returns:
            AppraisalResult: 感情評価結果。入力がない場合は SKIPPED。
        """
        text = interpreted_input_text(frame)
        if text is None:
            return AppraisalResult(
                step_name=self.name,
                status=StepStatus.SKIPPED,
                reason="no interpreted input text",
            )

        appraisal = classify_appraisal(text)
        mood = update_mood(frame.affect, appraisal, elapsed_seconds=self._elapsed_seconds)
        signals = self._classify_signals(text, frame)
        return AppraisalResult(
            step_name=self.name,
            status=StepStatus.OK,
            mood_label=mood.mood_label,
            arousal=mood.arousal,
            valence=mood.valence,
            dominance=mood.dominance,
            affect_summary=mood.affect_summary,
            appraisal_signals=signals,
            appraisal_summary=summarize_appraisal_signals(signals),
        )

    def _classify_signals(
        self,
        text: str,
        frame: WorkspaceFrame,
    ) -> tuple[AppraisalSignal, ...]:
        if not self._appraisal_signals_enabled:
            return ()
        return classify_appraisal_signals(
            text,
            source_observation_id=frame.observation.observation_id,
            dependency_risk_hint_enabled=self._dependency_risk_hint_enabled,
        )


def _build_signal(
    text: str,
    candidate: _SignalCandidate,
    source_observation_id: ObservationId | None,
) -> AppraisalSignal:
    return AppraisalSignal(
        kind=candidate.kind,
        label=candidate.label,
        polarity=candidate.polarity,
        confidence=candidate.confidence,
        reason=candidate.reason,
        source_span=_source_span(text, candidate.keywords),
        state_boundary=appraisal_state_boundary_for_kind(candidate.kind),
        safety_hint=candidate.safety_hint,
        source_observation_id=source_observation_id,
        metadata=_CLASSIFIER_METADATA,
    )


def _semantic_polarity(positive_hits: int, negative_hits: int) -> float:
    total = max(positive_hits + negative_hits, 1)
    return clamp_value((positive_hits - negative_hits) / total)


def _polarity_label(positive_label: str, negative_label: str, polarity: float) -> str:
    if polarity >= 0.0:
        return positive_label
    return negative_label


def _attitude_keywords(polarity: float) -> tuple[str, ...]:
    if polarity >= 0.0:
        return _GRATITUDE_KEYWORDS + _IRIS_REFERENCE_KEYWORDS + _POSITIVE_KEYWORDS
    return _IRIS_REFERENCE_KEYWORDS + _NEGATIVE_KEYWORDS


def _topic_keywords(polarity: float) -> tuple[str, ...]:
    if polarity >= 0.0:
        return _TOPIC_REFERENCE_KEYWORDS + _POSITIVE_KEYWORDS
    return _TOPIC_REFERENCE_KEYWORDS + _NEGATIVE_KEYWORDS


def _emotion_keywords(polarity: float) -> tuple[str, ...]:
    if polarity >= 0.0:
        return _USER_EMOTION_KEYWORDS + _POSITIVE_KEYWORDS
    return _USER_EMOTION_KEYWORDS + _NEGATIVE_KEYWORDS


def _implicit_direct_complaint(text: str) -> bool:
    return _matches_any(text, ("役に立たない", "使えない", "useless")) and not _matches_any(
        text,
        _TOPIC_REFERENCE_KEYWORDS,
    )


def _count_matches(text: str, keywords: tuple[str, ...]) -> int:
    tokens = tuple(match.group(0).casefold() for match in _TOKEN_RE.finditer(text))
    return sum(
        1 for keyword in keywords if keyword.casefold() in text or keyword.casefold() in tokens
    )


def _matches_any(text: str, keywords: tuple[str, ...]) -> bool:
    return _count_matches(text, keywords) > 0


def _source_span(text: str, keywords: tuple[str, ...]) -> AppraisalSourceSpan:
    keyword = _first_matching_keyword(text, keywords)
    if keyword is None:
        return AppraisalSourceSpan(start_index=0, end_index=len(text), text=text)
    lowered = text.casefold()
    start = lowered.find(keyword.casefold())
    end = start + len(keyword)
    return AppraisalSourceSpan(start_index=start, end_index=end, text=text[start:end])


def _first_matching_keyword(text: str, keywords: tuple[str, ...]) -> str | None:
    lowered = text.casefold()
    matches = tuple(
        (index, keyword)
        for keyword in keywords
        for index in (lowered.find(keyword.casefold()),)
        if index >= 0
    )
    if not matches:
        return None
    return min(matches, key=itemgetter(0))[1]
