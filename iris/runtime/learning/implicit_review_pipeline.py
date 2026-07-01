"""Runtime wiring helpers for implicit memory candidate review."""

from __future__ import annotations

from hashlib import sha256
import re
from typing import TYPE_CHECKING

from iris.cognitive.memory.candidates import MemoryCandidateSource, MemoryRetentionPolicy
from iris.contracts.learning import RuntimeLearningEventKind
from iris.contracts.observations import ObservationKind
from iris.core.metadata import immutable_metadata
from iris.runtime.learning.implicit_candidates import (
    ConservativeImplicitMemoryCandidateExtractor,
    EnqueueImplicitMemoryCandidateHook,
    ImplicitCandidateAdmissionPolicy,
    runtime_learning_event_to_payload,
)
from iris.runtime.learning.jobs import (
    BackgroundJobKind,
    BackgroundJobRecord,
    RuntimeLearningCandidateJobPayload,
)
from iris.runtime.state.memory_candidates import (
    MemoryCandidateReviewId,
    MemoryCandidateReviewRecord,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from iris.cognitive.memory.candidates import MemoryCandidate
    from iris.contracts.learning import RuntimeLearningEvent
    from iris.runtime.learning.queue import InMemoryBackgroundJobQueue
    from iris.runtime.state.memory_candidates import MemoryCandidateReviewStore

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


class FilteringImplicitMemoryCandidateHook:
    """Only enqueue extraction jobs for events that can produce review candidates."""

    def __init__(self, queue: InMemoryBackgroundJobQueue, *, max_attempts: int = 3) -> None:
        """Create a filtering hook around the built-in enqueue hook."""
        self._delegate = EnqueueImplicitMemoryCandidateHook(queue, max_attempts=max_attempts)

    async def after_runtime_event(self, event: RuntimeLearningEvent) -> None:
        """Skip ordinary conversation turns before they create background churn."""
        payload = self._delegate_payload(event)
        if payload is None or not has_review_candidate_signal(payload):
            return
        await self._delegate.after_runtime_event(event)

    @staticmethod
    def _delegate_payload(
        event: RuntimeLearningEvent,
    ) -> RuntimeLearningCandidateJobPayload | None:
        return runtime_learning_event_to_payload(event)


class AccountAwareImplicitMemoryCandidateWorker:
    """Store review candidates with actor/account/space boundary metadata."""

    kind = BackgroundJobKind.MEMORY_EXTRACTION

    def __init__(
        self,
        store: MemoryCandidateReviewStore,
        *,
        extractor: ConservativeImplicitMemoryCandidateExtractor | None = None,
        policy: ImplicitCandidateAdmissionPolicy | None = None,
    ) -> None:
        """Create a review-store worker."""
        self._store = store
        self._extractor = extractor or ConservativeImplicitMemoryCandidateExtractor()
        self._policy = policy or ImplicitCandidateAdmissionPolicy()

    def run(self, job: BackgroundJobRecord) -> None:
        """Extract accepted candidates and store them for explicit review.

        Raises:
            TypeError: job payload is not a runtime learning candidate payload.
        """
        payload = job.payload
        if not isinstance(payload, RuntimeLearningCandidateJobPayload):
            message = "implicit candidate extraction requires RuntimeLearningCandidateJobPayload"
            raise TypeError(message)
        for candidate in self._extractor.extract(payload):
            if not self._policy.accept(candidate):
                continue
            self._store.add_nowait(_review_record(job, payload, candidate))


def has_review_candidate_signal(payload: RuntimeLearningCandidateJobPayload) -> bool:
    """Return whether this payload can match the conservative extractor."""
    text = (payload.input_text or "").strip()
    if not text:
        return False
    if payload.event_kind is RuntimeLearningEventKind.USER_FEEDBACK:
        return True
    if payload.observation_kind is not ObservationKind.ACTOR_MESSAGE:
        return False
    return _matches_any(text, (*_RESPONSE_STYLE_PATTERNS, *_LANGUAGE_PREFERENCE_PATTERNS))


def _review_record(
    job: BackgroundJobRecord,
    payload: RuntimeLearningCandidateJobPayload,
    candidate: MemoryCandidate,
) -> MemoryCandidateReviewRecord:
    key = _candidate_key(job, candidate)
    return MemoryCandidateReviewRecord(
        candidate_id=MemoryCandidateReviewId(f"candidate-{key[:24]}"),
        candidate=candidate,
        created_at=job.created_at,
        updated_at=job.updated_at,
        idempotency_key=f"candidate:{key}",
        actor_id=payload.actor_id,
        account_id=payload.account_id,
        space_id=payload.space_id,
        source_observation_id=payload.source_observation_id,
        metadata=immutable_metadata(
            {
                "background_job_id": str(job.job_id),
                "runtime_event_kind": payload.event_kind.value,
                "source": MemoryCandidateSource.IMPLICIT_CONVERSATION.value,
                "retention_policy": MemoryRetentionPolicy.REVIEW_REQUIRED.value,
                "review_required": "true",
                "reason": candidate.reason or "",
            }
        ),
    )


def _candidate_key(job: BackgroundJobRecord, candidate: MemoryCandidate) -> str:
    material = (
        f"{job.idempotency_key}|{candidate.text}|{candidate.kind.value}|{candidate.source.value}"
    )
    return sha256(material.encode()).hexdigest()


def _matches_any(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)
