"""Tests for implicit candidate runtime wiring helpers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.contracts.actions import PresentedOutput
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.learning import RuntimeLearningEvent, RuntimeLearningEventKind
from iris.contracts.observations import ActorMessageObservation, ObservationContext, ObservationKind
from iris.core.ids import AccountId, ActorId, ExternalRef, ObservationId, SessionId, SpaceId
from iris.runtime.inference.policy import LocalInferenceResourcePolicy
from iris.runtime.inference.scheduler import LocalInferenceResourceScheduler
from iris.runtime.learning.implicit_candidates import (
    AccountAwareImplicitMemoryCandidateWorker,
    FilteringImplicitMemoryCandidateHook,
)
from iris.runtime.learning.policy import BackgroundJobKindPolicy, BackgroundJobQueuePolicy
from iris.runtime.learning.queue import InMemoryBackgroundJobQueue
from iris.runtime.learning.runner import (
    BackgroundJobRunner,
    BackgroundJobRunnerOptions,
    BackgroundJobRunnerRuntimeHooks,
)
from iris.runtime.state.memory_candidates import InMemoryMemoryCandidateReviewStore

pytestmark = pytest.mark.anyio

_NOW = datetime(2026, 7, 1, tzinfo=UTC)


async def test_filtering_hook_skips_ordinary_actor_message() -> None:
    """Filtering hook does not enqueue extraction jobs for ordinary actor messages."""
    queue = InMemoryBackgroundJobQueue()

    await FilteringImplicitMemoryCandidateHook(queue).after_runtime_event(_event("hello there"))

    assert await queue.lease_due(_NOW, 10, 30.0) == ()


async def test_filtering_hook_enqueues_preference_actor_message() -> None:
    """Filtering hook enqueues candidate extraction for preference signals."""
    queue = InMemoryBackgroundJobQueue()

    await FilteringImplicitMemoryCandidateHook(queue).after_runtime_event(
        _event("please answer briefly from now on")
    )

    assert len(await queue.lease_due(_NOW, 10, 30.0)) == 1


async def test_account_aware_worker_preserves_boundary_ids() -> None:
    """Account-aware worker stores actor, account, and space boundaries."""
    queue = InMemoryBackgroundJobQueue()
    store = InMemoryMemoryCandidateReviewStore()
    await FilteringImplicitMemoryCandidateHook(queue).after_runtime_event(
        _event("please answer briefly from now on")
    )

    await BackgroundJobRunner(
        queue,
        (AccountAwareImplicitMemoryCandidateWorker(store),),
        runtime_hooks=BackgroundJobRunnerRuntimeHooks(now=lambda: _NOW),
    ).run_once()

    record = (await store.list_pending())[0]
    assert record.actor_id == ActorId("actor-1")
    assert record.account_id == AccountId("account-1")
    assert record.space_id == SpaceId("space-1")


async def test_deterministic_implicit_worker_runs_when_inference_scheduler_is_enabled() -> None:
    """Deterministic implicit worker は scheduler 有効時も LLM lease なしで進む。"""
    queue = InMemoryBackgroundJobQueue()
    store = InMemoryMemoryCandidateReviewStore()
    await FilteringImplicitMemoryCandidateHook(queue).after_runtime_event(
        _event("please answer briefly from now on")
    )
    scheduler = LocalInferenceResourceScheduler(LocalInferenceResourcePolicy(enabled=True))

    processed = await BackgroundJobRunner(
        queue,
        (AccountAwareImplicitMemoryCandidateWorker(store),),
        options=BackgroundJobRunnerOptions(
            queue_policy=BackgroundJobQueuePolicy(
                per_kind={
                    AccountAwareImplicitMemoryCandidateWorker.kind: BackgroundJobKindPolicy(
                        uses_llm=False
                    )
                }
            ),
            runtime_hooks=BackgroundJobRunnerRuntimeHooks(now=lambda: _NOW),
            inference_scheduler=scheduler,
        ),
    ).run_once()

    assert processed == 1
    assert len(await store.list_pending()) == 1
    snapshot = await scheduler.snapshot()
    assert snapshot.active_large_slots == 0


async def test_review_store_filters_by_account_and_space() -> None:
    """Review store can isolate pending candidates by account and space."""
    queue = InMemoryBackgroundJobQueue()
    store = InMemoryMemoryCandidateReviewStore()
    await FilteringImplicitMemoryCandidateHook(queue).after_runtime_event(
        _event("please answer briefly from now on")
    )
    await BackgroundJobRunner(
        queue,
        (AccountAwareImplicitMemoryCandidateWorker(store),),
        runtime_hooks=BackgroundJobRunnerRuntimeHooks(now=lambda: _NOW),
    ).run_once()

    assert len(await store.list_pending(account_id=AccountId("account-1"))) == 1
    assert len(await store.list_pending(space_id=SpaceId("space-1"))) == 1
    assert await store.list_pending(account_id=AccountId("account-2")) == ()
    assert await store.list_pending(space_id=SpaceId("space-2")) == ()


def _event(text: str) -> RuntimeLearningEvent:
    observation = ActorMessageObservation(
        observation_id=ObservationId("obs-implicit-candidate-wiring"),
        session_id=SessionId("session-1"),
        context=ObservationContext(
            actor=Identity(
                actor_id=ActorId("actor-1"),
                actor_kind=ActorKind.HUMAN,
                display_name="Mina",
                provider="test",
                provider_subject=ExternalRef("user-1"),
            ),
            account_id=AccountId("account-1"),
            space_id=SpaceId("space-1"),
        ),
        occurred_at=_NOW,
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
    )
    return RuntimeLearningEvent(
        kind=RuntimeLearningEventKind.NO_ACTION,
        observation=observation,
        output=PresentedOutput(text=None),
        occurred_at=_NOW,
        route="cognitive",
        source_observation_id=observation.observation_id,
    )
