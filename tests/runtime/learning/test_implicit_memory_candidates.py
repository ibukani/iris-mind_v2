"""Implicit memory candidate pipeline tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.contracts.actions import PresentedOutput
from iris.contracts.appraisal import AppraisalSignal, AppraisalSignalKind, AppraisalSourceSpan
from iris.contracts.companion_affect import (
    CompanionAffectStateKind,
    CompanionInteractionScope,
)
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.learning import RuntimeLearningEvent, RuntimeLearningEventKind
from iris.contracts.memory import MemoryKind, MemoryQuery
from iris.contracts.memory_candidates import (
    MemoryCandidateSource,
    MemoryRetentionPolicy,
)
from iris.contracts.observations import (
    ActorMessageObservation,
    ObservationContext,
    ObservationKind,
    UserFeedbackKind,
    UserFeedbackObservation,
)
from iris.core.ids import ActorId, ExternalRef, ObservationId, SessionId, SpaceId
from iris.runtime.learning.implicit_candidates import (
    ConservativeImplicitMemoryCandidateExtractor,
    EnqueueImplicitMemoryCandidateHook,
    ImplicitCandidateAdmissionPolicy,
    ImplicitMemoryCandidateWorker,
    runtime_learning_event_to_payload,
)
from iris.runtime.learning.jobs import (
    BackgroundJobId,
    BackgroundJobKind,
    BackgroundJobRecord,
    RelationshipUpdateJobPayload,
    RuntimeLearningCandidateJobPayload,
)
from iris.runtime.learning.memory_worker import DeterministicMemoryConsolidationWorker
from iris.runtime.learning.queue import InMemoryBackgroundJobQueue
from iris.runtime.learning.relationship_worker import RelationshipUpdateCandidateWorker
from iris.runtime.learning.runner import BackgroundJobRunner, BackgroundJobRunnerRuntimeHooks
from iris.runtime.state.memory_candidates import (
    InMemoryMemoryCandidateReviewStore,
    MemoryCandidateReviewStatus,
)
from iris.runtime.state.relationship_updates import InMemoryRelationshipUpdateCandidateStore

pytestmark = pytest.mark.anyio

_NOW = datetime(2026, 7, 1, tzinfo=UTC)


async def test_runtime_hook_enqueues_implicit_candidate_job_idempotently() -> None:
    """Runtime eventから候補抽出jobを冪等に登録する。"""
    queue = InMemoryBackgroundJobQueue()
    hook = EnqueueImplicitMemoryCandidateHook(queue, max_attempts=4)
    event = _feedback_event("次からもっと短く答えて")

    await hook.after_runtime_event(event)
    await hook.after_runtime_event(event)

    leased = await queue.lease_due(_NOW, 10, 30.0)
    assert len(leased) == 1
    job = leased[0]
    assert job.kind is BackgroundJobKind.MEMORY_EXTRACTION
    assert job.max_attempts == 4
    assert isinstance(job.payload, RuntimeLearningCandidateJobPayload)
    assert job.resource_profile.uses_llm is False
    assert job.resource_profile.model_call_descriptor is None
    assert job.payload.source_observation_id == event.source_observation_id
    assert job.payload.input_text == "次からもっと短く答えて"


async def test_worker_stores_review_required_implicit_candidate() -> None:
    """Implicit候補はMemoryStoreではなくreview storeへ保存する。"""
    queue = InMemoryBackgroundJobQueue()
    review_store = InMemoryMemoryCandidateReviewStore()
    memory_store = InMemoryMemoryStore()
    relationship_store = InMemoryRelationshipUpdateCandidateStore()
    event = _feedback_event("次からもっと短く答えて")
    await EnqueueImplicitMemoryCandidateHook(queue).after_runtime_event(event)
    relationship_job = BackgroundJobRecord(
        job_id=BackgroundJobId("relationship-job-1"),
        kind=BackgroundJobKind.RELATIONSHIP_UPDATE,
        payload=RelationshipUpdateJobPayload(
            signals=(
                AppraisalSignal(
                    kind=AppraisalSignalKind.ATTITUDE_TOWARD_IRIS,
                    label="positive-attitude",
                    polarity=0.8,
                    confidence=0.9,
                    reason="user thanked Iris",
                    source_span=AppraisalSourceSpan(start_index=0, end_index=5, text="ありがとう"),
                    state_boundary=CompanionAffectStateKind.ACTOR_RELATIONSHIP,
                    source_observation_id=ObservationId("obs-relationship"),
                ),
            ),
            interaction_scope=CompanionInteractionScope.DIRECT_MESSAGE,
            actor_id=ActorId("actor-1"),
            account_id=None,
            source_observation_id=ObservationId("obs-relationship"),
            source_event_ids=("event-relationship-1",),
        ),
        not_before=_NOW,
        idempotency_key="relationship-job-key-1",
        created_at=_NOW,
        updated_at=_NOW,
    )
    await queue.enqueue(relationship_job)

    relationship_worker = RelationshipUpdateCandidateWorker(relationship_store)
    runner = BackgroundJobRunner(
        queue,
        (
            DeterministicMemoryConsolidationWorker(memory_store),
            ImplicitMemoryCandidateWorker(review_store),
            relationship_worker,
        ),
        runtime_hooks=BackgroundJobRunnerRuntimeHooks(now=lambda: _NOW),
    )

    assert await runner.run_once() == 2
    pending = await review_store.list_pending()
    assert len(pending) == 1
    record = pending[0]
    assert record.status is MemoryCandidateReviewStatus.PENDING_REVIEW
    assert record.candidate.source is MemoryCandidateSource.IMPLICIT_CONVERSATION
    assert record.candidate.retention_policy is MemoryRetentionPolicy.REVIEW_REQUIRED
    assert record.candidate.review_required is True
    assert record.candidate.reason
    assert record.candidate.confidence >= 0.35
    assert record.candidate.kind is MemoryKind.PREFERENCE
    assert record.candidate.source_observation_id == event.source_observation_id
    assert record.metadata["source"] == MemoryCandidateSource.IMPLICIT_CONVERSATION.value
    assert memory_store.search(MemoryQuery(text="短く", limit=10)) == ()
    relationship_worker.run(relationship_job)
    relationship_worker.run(relationship_job)
    assert len(relationship_store.list_records()) == 1
    relationship_record = relationship_store.list_records()[0]
    assert relationship_record.actor_id == ActorId("actor-1")
    assert relationship_record.interaction_scope is CompanionInteractionScope.DIRECT_MESSAGE
    assert relationship_record.candidate.decision_kind.value == "automatic_bounded"
    assert relationship_record.candidate.source_event_ids == ("event-relationship-1",)
    assert relationship_record.candidate.source_observation_ids == (
        ObservationId("obs-relationship"),
    )


def test_actor_message_style_preference_becomes_review_candidate() -> None:
    """通常会話内の応答スタイル嗜好もreview-required候補として扱う。"""
    payload = runtime_learning_event_to_payload(
        _actor_event("これから短めに答えてください", RuntimeLearningEventKind.NO_ACTION)
    )
    assert payload is not None

    candidates = ConservativeImplicitMemoryCandidateExtractor().extract(payload)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.source is MemoryCandidateSource.IMPLICIT_CONVERSATION
    assert candidate.retention_policy is MemoryRetentionPolicy.REVIEW_REQUIRED
    assert candidate.review_required is True
    assert candidate.kind is MemoryKind.PREFERENCE
    assert candidate.actor_id == ActorId("actor-1")
    assert candidate.space_id == SpaceId("space-1")


async def test_secret_like_feedback_is_not_stored_for_review() -> None:
    """Credential-like内容はreview storeにも残さない。"""
    queue = InMemoryBackgroundJobQueue()
    review_store = InMemoryMemoryCandidateReviewStore()
    hook = EnqueueImplicitMemoryCandidateHook(queue)
    await hook.after_runtime_event(_feedback_event("API key is sk-test-1234567890abcdef"))

    await BackgroundJobRunner(
        queue,
        (ImplicitMemoryCandidateWorker(review_store),),
        runtime_hooks=BackgroundJobRunnerRuntimeHooks(now=lambda: _NOW),
    ).run_once()

    assert await review_store.list_pending() == ()


async def test_low_confidence_candidates_are_rejected_by_admission_policy() -> None:
    """信頼度しきい値未満はreview storeにも入れない。"""
    queue = InMemoryBackgroundJobQueue()
    review_store = InMemoryMemoryCandidateReviewStore()
    hook = EnqueueImplicitMemoryCandidateHook(queue)
    await hook.after_runtime_event(_feedback_event("了解", kind=UserFeedbackKind.OTHER))

    await BackgroundJobRunner(
        queue,
        (
            ImplicitMemoryCandidateWorker(
                review_store,
                policy=ImplicitCandidateAdmissionPolicy(min_confidence=0.5),
            ),
        ),
        runtime_hooks=BackgroundJobRunnerRuntimeHooks(now=lambda: _NOW),
    ).run_once()

    assert await review_store.list_pending() == ()


async def test_review_store_deduplicates_candidate_records() -> None:
    """同じjobを再処理しても候補は重複しない。"""
    queue = InMemoryBackgroundJobQueue()
    review_store = InMemoryMemoryCandidateReviewStore()
    hook = EnqueueImplicitMemoryCandidateHook(queue)
    await hook.after_runtime_event(_feedback_event("次からもっと短く答えて"))
    job = (await queue.lease_due(_NOW, 1, 30.0))[0]
    worker = ImplicitMemoryCandidateWorker(review_store)

    worker.run(job)
    worker.run(job)

    assert len(await review_store.list_pending()) == 1


def _feedback_event(
    text: str,
    *,
    kind: UserFeedbackKind = UserFeedbackKind.STYLE_PREFERENCE,
) -> RuntimeLearningEvent:
    observation = UserFeedbackObservation(
        observation_id=ObservationId("obs-feedback-implicit"),
        session_id=SessionId("session-1"),
        context=_context(),
        occurred_at=_NOW,
        kind=ObservationKind.USER_FEEDBACK,
        feedback_kind=kind,
        text=text,
    )
    return RuntimeLearningEvent(
        kind=RuntimeLearningEventKind.USER_FEEDBACK,
        observation=observation,
        output=None,
        occurred_at=_NOW,
        route="user_feedback",
        source_observation_id=observation.observation_id,
    )


def _actor_event(text: str, kind: RuntimeLearningEventKind) -> RuntimeLearningEvent:
    observation = ActorMessageObservation(
        observation_id=ObservationId("obs-actor-implicit"),
        session_id=SessionId("session-1"),
        context=_context(),
        occurred_at=_NOW,
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
    )
    return RuntimeLearningEvent(
        kind=kind,
        observation=observation,
        output=PresentedOutput(text=None),
        occurred_at=_NOW,
        route="cognitive",
        source_observation_id=observation.observation_id,
    )


def _context() -> ObservationContext:
    return ObservationContext(
        actor=Identity(
            actor_id=ActorId("actor-1"),
            actor_kind=ActorKind.HUMAN,
            display_name="Mina",
            provider="test",
            provider_subject=ExternalRef("user-1"),
        ),
        space_id=SpaceId("space-1"),
    )
