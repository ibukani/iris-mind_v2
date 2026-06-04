"""プロアクティブ発話の顕著性スコアリングロジック。"""

from __future__ import annotations

from iris.contracts.observations import IdleTickObservation
from iris.features.proactive_talk.models import ProactiveFrameContext, ProactiveSalience

_MAX_IDLE_SECONDS = 600.0
_IDLE_WEIGHT = 0.7
_MEMORY_BOOST = 0.15
_LOW_FAMILIARITY_PENALTY = 0.15
_HIGH_FAMILIARITY_BOOST = 0.05
_NEGATIVE_AFFECT_PENALTY = 0.25
_POSITIVE_AFFECT_BOOST = 0.05
_LOW_FAMILIARITY_THRESHOLD = 0.2
_HIGH_FAMILIARITY_THRESHOLD = 0.6
_HIGH_AROUSAL_THRESHOLD = 0.75
_NEGATIVE_VALENCE_THRESHOLD = -0.55
_POSITIVE_VALENCE_THRESHOLD = 0.3


class SalienceScorer:
    """フレームコンテキストからプロアクティブ発話の顕著性を計算する。"""

    def __init__(self, threshold: float = 0.5) -> None:
        """顕著性の閾値で初期化する。

        Args:
            threshold: Minimum score required for proactive talk.
        """
        self._threshold = threshold

    def score(self, frame: ProactiveFrameContext) -> ProactiveSalience:
        """フレームをスコアリングし、顕著性結果を返す。

        Returns:
            ProactiveSalience: フレームの顕著性スコアと判定結果。
        """
        if not isinstance(frame.observation, IdleTickObservation):
            return ProactiveSalience(
                score=0.0,
                threshold=self._threshold,
                reasons=("not_idle_tick",),
            )

        if any(constraint.blocks_response for constraint in frame.constraints):
            return ProactiveSalience(
                score=0.0,
                threshold=self._threshold,
                reasons=("policy_block",),
                blocked=True,
            )

        score = _idle_score(frame.observation.idle_seconds)
        reasons = [f"idle_seconds={frame.observation.idle_seconds:.1f}"]

        if frame.memory_summary.retrieved_memories:
            score += _MEMORY_BOOST
            reasons.append("memory_context")

        score = _apply_relationship_score(
            score, reasons, frame.relationship.actor_label, frame.relationship.familiarity
        )
        score = _apply_affect_score(score, reasons, frame.affect.arousal, frame.affect.valence)

        bounded_score = max(0.0, min(1.0, score))
        return ProactiveSalience(
            score=bounded_score,
            threshold=self._threshold,
            reasons=tuple(reasons),
        )


def _idle_score(idle_seconds: float) -> float:
    bounded_idle = max(0.0, min(_MAX_IDLE_SECONDS, idle_seconds))
    return (bounded_idle / _MAX_IDLE_SECONDS) * _IDLE_WEIGHT


def _apply_relationship_score(
    score: float, reasons: list[str], actor_label: str | None, familiarity: float
) -> float:
    if actor_label is None:
        return score
    if familiarity < _LOW_FAMILIARITY_THRESHOLD:
        score -= _LOW_FAMILIARITY_PENALTY
        reasons.append("low_familiarity")
    elif familiarity > _HIGH_FAMILIARITY_THRESHOLD:
        score += _HIGH_FAMILIARITY_BOOST
        reasons.append("high_familiarity")
    return score


def _apply_affect_score(score: float, reasons: list[str], arousal: float, valence: float) -> float:
    if arousal > _HIGH_AROUSAL_THRESHOLD and valence < _NEGATIVE_VALENCE_THRESHOLD:
        score -= _NEGATIVE_AFFECT_PENALTY
        reasons.append("negative_high_arousal")
    elif valence > _POSITIVE_VALENCE_THRESHOLD:
        score += _POSITIVE_AFFECT_BOOST
        reasons.append("positive_affect")
    return score
