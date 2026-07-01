"""Implicit conversation learning candidate pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from typing import TYPE_CHECKING

from iris.cognitive.memory.candidates import (
    MemoryCandidate,
    MemoryCandidateSensitivity,
    MemoryCandidateSource,
    MemoryRetentionPolicy,
)
from iris.cognitive.memory.safety import (
    contains_credential_like_content,
    contains_sensitive_profile_content,
)
from iris.contracts.learning import RuntimeLearningEventKind
from iris.contracts.memory import MemoryKind
from iris.contracts.observations import ObservationKind, UserFeedbackKind
from iris.core.metadata import immutable_metadata
from iris.runtime.learning.jobs import (
    BackgroundJobId,
    BackgroundJobKind,
    BackgroundJobRecord,
    RuntimeLearningCandidateJobPayload,
)
from iris.runtime.observation_router import actor_message_observation, user_feedback_observation

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from iris.contracts.learning import RuntimeLearningEvent
    from iris.runtime.learning.queue import InMemoryBackgroundJobQueue

_RESPONSE_STYLE_PATTERNS = (
    r"(?:今後|これから|以後|次から).*(?:短め|短く|簡潔|端的).*(?:答えて|回答して|返して)",
    r"(?:短め|短く|簡潔|端的).*(?:答えて|回答して|返して).*(?:今後|これから|以後|次から)",
    r"(?:please\s+)?(?:answer|respond|reply)\s+(?:briefly|concisely)\s+from now on",
    r"keep (?:your )?(?:answers|responses|replies) (?:short|brief|concise)",
)
_LANGUAGE_PREFERENCE_PATTERNS = (
    r"(?:今後|これから|以後|次から)?.*日本語で(?:答えて|回答して|返して)ほしい?",
    r"(?:please\s+)?(?:answer|respond|reply)\s+in Japanese",
)
_POSITIVE_FEEDBACK = (
    "いい感じ",
    "良かった",
    "助かった",
    "ありがとう",
    "good answer",
    "that helped",
    "thanks",
)
_NEGATIVE_FEEDBACK = (
    "嫌",
    "違う",
    "やめて",
    "bad answer",
    "not helpful",
    "wrong",
)
_REVIEWABLE_SENSITIVITY = frozenset(
    {
        MemoryCandidateSensitivity.NORMAL,
        MemoryCandidateSensitivity.PERSONAL,
        MemoryCandidateSensitivity.SENSITIVE,
    }
)


class EnqueueImplicitMemoryCandidateHook:
    """Runtime learning eventsをimplicit candidate extraction jobへ変換するhook。"""

    def __init__(
        self,
        queue: InMemoryBackgroundJobQueue,
        *,
        max_attempts: int = 3,
    ) -> None:
        """キューと再試行上限を注入する。"""
        self._queue = queue
        self._max_attempts = max_attempts

    async def after_runtime_event(self, event: RuntimeLearningEvent) -> None:
        """学習シグナルがあるruntime eventだけを冪等にenqueueする。"""
        payload = runtime_learning_event_to_payload(event)
        if payload is None or not has_implicit_candidate_signal(payload):
            return
        key = _job_key(payload)
        await self._queue.enqueue(_new_job(key, payload, event.occurred_at, self._max_attempts))


class ConservativeImplicitMemoryCandidateExtractor:
    """LLMを使わず、review-required候補だけを作る保守的抽出器。"""

    @staticmethod
    def extract(
        payload: RuntimeLearningCandidateJobPayload,
    ) -> tuple[MemoryCandidate, ...]:
        """Runtime event payloadから候補を抽出する。

        Returns:
            Durable memoryではなくreview store向けの候補列。
        """
        text = (payload.input_text or "").strip()
        if payload.event_kind is RuntimeLearningEventKind.USER_FEEDBACK:
            return _feedback_candidates(payload, text)
        if payload.observation_kind is not ObservationKind.ACTOR_MESSAGE:
            return ()
        return _actor_message_candidates(payload, text)


@dataclass(frozen=True)
class _CandidateSpec:
    text: str
    kind: MemoryKind
    salience: float
    confidence: float
    reason: str
    sensitivity: MemoryCandidateSensitivity


@dataclass(frozen=True)
class ImplicitCandidateAdmissionPolicy:
    """Implicit candidateをreview storeに入れてよいか判定する。"""

    min_confidence: float = 0.35
    max_text_length: int = 1000
    allow_sensitive_review_candidates: bool = False

    def accept(self, candidate: MemoryCandidate) -> bool:
        """Review candidateとして受け入れるか判定する。

        Returns:
            Review storeへ保存してよい場合はTrue。
        """
        text = candidate.text.strip()
        return (
            self._content_is_valid(text, candidate)
            and self._provenance_is_valid(candidate)
            and self._safety_is_valid(text, candidate)
        )

    def _content_is_valid(self, text: str, candidate: MemoryCandidate) -> bool:
        return (
            bool(text)
            and len(text) <= self.max_text_length
            and candidate.confidence >= self.min_confidence
        )

    @staticmethod
    def _provenance_is_valid(candidate: MemoryCandidate) -> bool:
        return (
            candidate.source is MemoryCandidateSource.IMPLICIT_CONVERSATION
            and candidate.retention_policy is MemoryRetentionPolicy.REVIEW_REQUIRED
            and candidate.review_required
        )

    def _safety_is_valid(self, text: str, candidate: MemoryCandidate) -> bool:
        if contains_credential_like_content(text):
            return False
        if candidate.sensitivity is MemoryCandidateSensitivity.SECRET_LIKE:
            return False
        if contains_sensitive_profile_content(text) and not self.allow_sensitive_review_candidates:
            return False
        return candidate.sensitivity in _REVIEWABLE_SENSITIVITY


def runtime_learning_event_to_payload(
    event: RuntimeLearningEvent,
) -> RuntimeLearningCandidateJobPayload | None:
    """RuntimeLearningEventをbackground job payloadへ落とす。

    Returns:
        候補抽出に必要なtyped payload。学習シグナルがなければNone。
    """
    observation = event.observation
    input_text: str | None = None
    feedback_kind: UserFeedbackKind | None = None
    actor_message = actor_message_observation(observation)
    user_feedback = user_feedback_observation(observation)
    if actor_message is not None:
        input_text = actor_message.text
    elif user_feedback is not None:
        input_text = user_feedback.text
        feedback_kind = user_feedback.feedback_kind
    elif event.kind is not RuntimeLearningEventKind.USER_FEEDBACK:
        return None

    output_text = event.output.text if event.output is not None else None
    if not (input_text and input_text.strip()) and not (output_text and output_text.strip()):
        return None
    context = observation.context
    return RuntimeLearningCandidateJobPayload(
        event_kind=event.kind,
        route=event.route,
        observation_kind=observation.kind,
        input_text=input_text,
        output_text=output_text,
        feedback_kind=feedback_kind,
        actor_id=context.actor_id,
        account_id=context.account_id,
        space_id=context.space_id,
        session_id=observation.session_id,
        source_observation_id=event.source_observation_id,
        occurred_at=event.occurred_at,
    )


def has_implicit_candidate_signal(payload: RuntimeLearningCandidateJobPayload) -> bool:
    """Cheaply decide whether extraction could produce any candidate.

    This avoids queue churn for ordinary conversation turns that cannot match
    the conservative extractor.

    Returns:
        True when a background extraction job is worthwhile.
    """
    text = (payload.input_text or "").strip()
    if not text:
        return False
    if payload.event_kind is RuntimeLearningEventKind.USER_FEEDBACK:
        return True
    if payload.observation_kind is not ObservationKind.ACTOR_MESSAGE:
        return False
    return _matches_any(text, (*_RESPONSE_STYLE_PATTERNS, *_LANGUAGE_PREFERENCE_PATTERNS))


def _feedback_candidates(
    payload: RuntimeLearningCandidateJobPayload,
    text: str,
) -> tuple[MemoryCandidate, ...]:
    if not text:
        return ()
    confidence = _feedback_confidence(payload.feedback_kind, text)
    kind = _feedback_memory_kind(payload.feedback_kind)
    reason = _feedback_reason(payload.feedback_kind)
    return (
        _candidate(
            payload,
            _CandidateSpec(
                text=_feedback_text(payload.feedback_kind, text),
                kind=kind,
                salience=0.65,
                confidence=confidence,
                reason=reason,
                sensitivity=_sensitivity_for_text(text),
            ),
        ),
    )


def _actor_message_candidates(
    payload: RuntimeLearningCandidateJobPayload,
    text: str,
) -> tuple[MemoryCandidate, ...]:
    if not text:
        return ()
    candidates: list[MemoryCandidate] = []
    if _matches_any(text, _RESPONSE_STYLE_PATTERNS):
        candidates.append(
            _candidate(
                payload,
                _CandidateSpec(
                    text=f"ユーザーはIrisの返答スタイルについて次の嗜好を示した: {text}",
                    kind=MemoryKind.PREFERENCE,
                    salience=0.6,
                    confidence=0.55,
                    reason="implicit response style preference from conversation",
                    sensitivity=_sensitivity_for_text(text),
                ),
            )
        )
    if _matches_any(text, _LANGUAGE_PREFERENCE_PATTERNS):
        candidates.append(
            _candidate(
                payload,
                _CandidateSpec(
                    text=f"ユーザーは応答言語について次の嗜好を示した: {text}",
                    kind=MemoryKind.PREFERENCE,
                    salience=0.6,
                    confidence=0.55,
                    reason="implicit language preference from conversation",
                    sensitivity=_sensitivity_for_text(text),
                ),
            )
        )
    return tuple(candidates)


def _candidate(
    payload: RuntimeLearningCandidateJobPayload,
    spec: _CandidateSpec,
) -> MemoryCandidate:
    return MemoryCandidate(
        text=spec.text.strip(),
        kind=spec.kind,
        salience=spec.salience,
        confidence=spec.confidence,
        source=MemoryCandidateSource.IMPLICIT_CONVERSATION,
        reason=spec.reason,
        retention_policy=MemoryRetentionPolicy.REVIEW_REQUIRED,
        sensitivity=spec.sensitivity,
        review_required=True,
        actor_id=payload.actor_id,
        space_id=payload.space_id,
        source_observation_id=payload.source_observation_id,
        metadata=immutable_metadata(
            {
                "runtime_event_kind": payload.event_kind.value,
                "runtime_route": payload.route,
                "observation_kind": payload.observation_kind.value,
            }
        ),
    )


def _feedback_text(feedback_kind: UserFeedbackKind | None, text: str) -> str:
    if feedback_kind is UserFeedbackKind.STYLE_PREFERENCE:
        return f"ユーザーはIrisの応答スタイルについて次のフィードバックをした: {text}"
    if feedback_kind is UserFeedbackKind.CORRECTION:
        return f"ユーザーはIrisの応答内容について次の訂正フィードバックをした: {text}"
    return f"ユーザーはIrisへのフィードバックとして次を伝えた: {text}"


def _feedback_confidence(feedback_kind: UserFeedbackKind | None, text: str) -> float:
    if feedback_kind in {UserFeedbackKind.STYLE_PREFERENCE, UserFeedbackKind.CORRECTION}:
        return 0.6
    lowered = text.casefold()
    if any(marker in lowered for marker in (*_POSITIVE_FEEDBACK, *_NEGATIVE_FEEDBACK)):
        return 0.45
    return 0.4


def _feedback_memory_kind(feedback_kind: UserFeedbackKind | None) -> MemoryKind:
    if feedback_kind is UserFeedbackKind.STYLE_PREFERENCE:
        return MemoryKind.PREFERENCE
    if feedback_kind in {UserFeedbackKind.POSITIVE, UserFeedbackKind.NEGATIVE}:
        return MemoryKind.RELATIONSHIP_EVENT
    return MemoryKind.NOTE


def _feedback_reason(feedback_kind: UserFeedbackKind | None) -> str:
    if feedback_kind is UserFeedbackKind.STYLE_PREFERENCE:
        return "user feedback may indicate a stable response-style preference"
    if feedback_kind is UserFeedbackKind.CORRECTION:
        return "user feedback may correct assistant behavior or understanding"
    return "user feedback may be useful for future relationship or behavior adjustment"


def _sensitivity_for_text(text: str) -> MemoryCandidateSensitivity:
    if contains_credential_like_content(text):
        return MemoryCandidateSensitivity.SECRET_LIKE
    if contains_sensitive_profile_content(text):
        return MemoryCandidateSensitivity.SENSITIVE
    return MemoryCandidateSensitivity.NORMAL


def _matches_any(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _job_key(payload: RuntimeLearningCandidateJobPayload) -> str:
    material = "|".join(
        (
            payload.event_kind.value,
            payload.route,
            str(payload.source_observation_id),
            payload.input_text or "",
            payload.output_text or "",
        )
    )
    return sha256(material.encode()).hexdigest()


def _new_job(
    key: str,
    payload: RuntimeLearningCandidateJobPayload,
    now: datetime,
    max_attempts: int,
) -> BackgroundJobRecord:
    return BackgroundJobRecord(
        job_id=BackgroundJobId(f"implicit-memory-{key[:24]}"),
        kind=BackgroundJobKind.MEMORY_EXTRACTION,
        payload=payload,
        max_attempts=max_attempts,
        not_before=now,
        idempotency_key=f"implicit-memory:{key}",
        created_at=now,
        updated_at=now,
    )
