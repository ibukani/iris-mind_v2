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


class SalienceScorer:
    def __init__(self, threshold: float = 0.5) -> None:
        self._threshold = threshold

    def score(self, frame: ProactiveFrameContext) -> ProactiveSalience:
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

        if frame.relationship.user_label is not None:
            if frame.relationship.familiarity < 0.2:
                score -= _LOW_FAMILIARITY_PENALTY
                reasons.append("low_familiarity")
            elif frame.relationship.familiarity > 0.6:
                score += _HIGH_FAMILIARITY_BOOST
                reasons.append("high_familiarity")

        if frame.affect.arousal > 0.75 and frame.affect.valence < -0.55:
            score -= _NEGATIVE_AFFECT_PENALTY
            reasons.append("negative_high_arousal")
        elif frame.affect.valence > 0.3:
            score += _POSITIVE_AFFECT_BOOST
            reasons.append("positive_affect")

        bounded_score = max(0.0, min(1.0, score))
        return ProactiveSalience(
            score=bounded_score,
            threshold=self._threshold,
            reasons=tuple(reasons),
        )


def _idle_score(idle_seconds: float) -> float:
    bounded_idle = max(0.0, min(_MAX_IDLE_SECONDS, idle_seconds))
    return (bounded_idle / _MAX_IDLE_SECONDS) * _IDLE_WEIGHT
