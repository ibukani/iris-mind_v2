"""Runtime latency budget observability tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.llm.observability import ObservableLLMClient
from iris.contracts.actions import PresentedOutput
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.learning import RuntimeLearningEvent, RuntimeLearningEventKind
from iris.contracts.observations import ActorMessageObservation, ObservationContext, ObservationKind
from iris.core.ids import ActorId, CorrelationId, ObservationId, SessionId, SpaceId
from iris.runtime.conversation import ShortTermConversationRuntime
from iris.runtime.learning.implicit_candidates import EnqueueImplicitMemoryCandidateHook
from iris.runtime.learning.queue import InMemoryBackgroundJobQueue
from iris.runtime.observability.context import RuntimeTraceContext, bind_trace_context
from iris.runtime.observability.llm import RuntimeLLMRequestObserver
from iris.runtime.observability.ports import (
    RuntimeLatencyBudget,
    RuntimeLatencyStage,
    RuntimeLogFields,
    RuntimeLogValue,
)
from iris.runtime.observability.timing import RuntimeLatencyRecorder
from iris.runtime.service import IrisRuntimeService, ObservationEnvelope, RuntimeServiceExtensions
from iris.runtime.state.conversation import InMemoryConversationHistoryStore
from iris.runtime.wiring.app import wire_default_app
from tests.helpers.approx import approx
from tests.helpers.transcript import InMemoryTranscriptStore


class _RecordingObserver:
    """Runtime observation observer fake."""

    def __init__(self) -> None:
        self.events: list[tuple[str, RuntimeLogFields]] = []

    def record(self, event: str, **fields: RuntimeLogValue) -> None:
        """Record an event."""
        self.events.append((event, fields))


class _RecordingRuntimeLogger:
    """Runtime logger fake."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str, RuntimeLogFields]] = []

    def debug(self, event: str, **fields: RuntimeLogValue) -> None:
        """Record a debug event."""
        self.events.append(("debug", event, fields))

    def info(self, event: str, **fields: RuntimeLogValue) -> None:
        """Record an info event."""
        self.events.append(("info", event, fields))

    def warning(self, event: str, **fields: RuntimeLogValue) -> None:
        """Record a warning event."""
        self.events.append(("warning", event, fields))

    def error(self, event: str, **fields: RuntimeLogValue) -> None:
        """Record an error event."""
        self.events.append(("error", event, fields))


class _NoOpRuntimeLearningRunner:
    """Runtime learning runner fake."""

    async def run(self, event: RuntimeLearningEvent) -> None:
        """Accept runtime learning events without side effects."""
        del event


def _trace_context() -> RuntimeTraceContext:
    return RuntimeTraceContext(
        correlation_id="corr-1",
        observation_id="obs-1",
        observation_kind="actor_message",
        ingress_kind="external_client",
        adapter_id=None,
        provider=None,
        actor_id="actor-1",
        space_id="space-1",
    )


def _message(text: str = "secret user text") -> ActorMessageObservation:
    return ActorMessageObservation(
        observation_id=ObservationId("obs-1"),
        session_id=SessionId("session-1"),
        context=ObservationContext(
            actor=Identity(
                actor_id=ActorId("actor-1"),
                actor_kind=ActorKind.HUMAN,
                display_name="Ada",
            ),
            space_id=SpaceId("space-1"),
        ),
        occurred_at=datetime(2026, 7, 1, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
    )


def _stage_names(observer: _RecordingObserver) -> set[str]:
    return {
        str(fields["stage"])
        for event, fields in observer.events
        if event == "runtime.latency.stage"
    }


def _slow_stage_names(observer: _RecordingObserver) -> set[str]:
    return {
        str(fields["stage"]) for event, fields in observer.events if event == "runtime.latency.slow"
    }


def test_latency_recorder_emits_stage_and_slow_warning() -> None:
    """Budget exceeded stage emits a structured latency sample and slow warning."""
    observer = _RecordingObserver()
    recorder = RuntimeLatencyRecorder(
        observer,
        RuntimeLatencyBudget(handle_observation_ms=1.0),
    )

    with bind_trace_context(_trace_context()):
        recorder.record_stage(
            RuntimeLatencyStage.HANDLE_OBSERVATION,
            latency_ms=2.0,
            output_present=True,
        )

    assert [event for event, _ in observer.events] == [
        "runtime.latency.stage",
        "runtime.latency.slow",
    ]
    fields = observer.events[0][1]
    assert fields["stage"] == "handle_observation"
    assert fields["latency_ms"] == approx(2.0)
    assert fields["budget_ms"] == approx(1.0)
    assert fields["budget_exceeded"] is True
    assert fields["output_present"] is True
    assert fields["correlation_id"] == "corr-1"
    assert fields["model_call_count"] == 0


def test_latency_budget_can_disable_stage_events() -> None:
    """Disabled latency budget makes the recorder a no-op."""
    observer = _RecordingObserver()
    recorder = RuntimeLatencyRecorder(
        observer,
        RuntimeLatencyBudget(enabled=False),
    )

    recorder.record_stage(RuntimeLatencyStage.HANDLE_OBSERVATION, latency_ms=2.0)

    assert observer.events == []


@pytest.mark.anyio
async def test_runtime_service_records_required_response_path_stages() -> None:
    """RuntimeService records stage latency for the user-facing response path."""
    observer = _RecordingObserver()
    service = IrisRuntimeService(
        wire_default_app(FakeLLMClient(responses=("ok",))),
        extensions=RuntimeServiceExtensions(
            observation_observer=observer,
            runtime_learning_hook_runner=_NoOpRuntimeLearningRunner(),
        ),
    )

    await service.handle_observation(
        ObservationEnvelope.external_client(
            observation=_message(),
            correlation_id=CorrelationId("corr-1"),
        ),
    )

    assert {
        "handle_observation",
        "observation_integration",
        "workspace_context_assembly",
        "conversation_context_load",
        "cognitive_processing",
        "conversation_record",
        "runtime_learning_hook",
    }.issubset(_stage_names(observer))
    assert all(fields["correlation_id"] == "corr-1" for _, fields in observer.events)


@pytest.mark.anyio
async def test_runtime_service_events_include_llm_model_call_count() -> None:
    """LLM observer increments request-local model call count for runtime events."""
    observer = _RecordingObserver()
    llm_logger = _RecordingRuntimeLogger()
    client = ObservableLLMClient(
        FakeLLMClient(responses=("ok",)),
        RuntimeLLMRequestObserver(llm_logger),
    )
    service = IrisRuntimeService(
        wire_default_app(client),
        extensions=RuntimeServiceExtensions(observation_observer=observer),
    )

    await service.handle_observation(
        ObservationEnvelope.external_client(
            observation=_message(),
            correlation_id=CorrelationId("corr-1"),
        ),
    )

    success_fields = next(
        fields for event, fields in observer.events if event == "runtime.observation.success"
    )
    llm_stage_fields = next(
        fields for _, event, fields in llm_logger.events if event == "runtime.latency.stage"
    )

    assert success_fields["model_call_count"] == 1
    assert llm_stage_fields["stage"] == "llm_generate"
    assert llm_stage_fields["model_call_count"] == 1
    assert llm_stage_fields["model_load_state"] == "unknown"


@pytest.mark.anyio
async def test_runtime_learning_hook_slow_warning_is_recorded() -> None:
    """Runtime learning hook over budget emits a slow warning."""
    observer = _RecordingObserver()
    service = IrisRuntimeService(
        wire_default_app(FakeLLMClient(responses=("ok",))),
        extensions=RuntimeServiceExtensions(
            observation_observer=observer,
            runtime_learning_hook_runner=_NoOpRuntimeLearningRunner(),
            latency_budget=RuntimeLatencyBudget(runtime_learning_hook_ms=0.000001),
        ),
    )

    await service.handle_observation(
        ObservationEnvelope.external_client(
            observation=_message(),
            correlation_id=CorrelationId("corr-1"),
        ),
    )

    assert "runtime_learning_hook" in _slow_stage_names(observer)


@pytest.mark.anyio
async def test_transcript_append_latency_is_observable() -> None:
    """ShortTermConversationRuntime records transcript append latency."""
    observer = _RecordingObserver()
    runtime = ShortTermConversationRuntime(
        InMemoryConversationHistoryStore(),
        transcript_store=InMemoryTranscriptStore(),
        observation_observer=observer,
    )

    await runtime.record_response(_message(), PresentedOutput(text="reply"))

    assert "transcript_append" in _stage_names(observer)


@pytest.mark.anyio
async def test_background_enqueue_latency_is_observable() -> None:
    """Implicit memory candidate enqueue records background enqueue latency."""
    observer = _RecordingObserver()
    hook = EnqueueImplicitMemoryCandidateHook(
        InMemoryBackgroundJobQueue(),
        observation_observer=observer,
    )

    await hook.after_runtime_event(
        RuntimeLearningEvent(
            kind=RuntimeLearningEventKind.INLINE_RESPONSE_GENERATED,
            observation=_message("これから短く答えて"),
            output=PresentedOutput(text="ok"),
            occurred_at=datetime(2026, 7, 1, tzinfo=UTC),
            route="cognitive",
            source_observation_id=ObservationId("obs-1"),
        )
    )

    assert "background_enqueue" in _stage_names(observer)


def test_latency_events_do_not_include_user_text() -> None:
    """Latency events do not contain user text or prompt text."""
    observer = _RecordingObserver()
    recorder = RuntimeLatencyRecorder(observer)

    with bind_trace_context(_trace_context()):
        recorder.record_stage(RuntimeLatencyStage.HANDLE_OBSERVATION, latency_ms=1.0)

    rendered = repr(observer.events)
    assert "secret user text" not in rendered
    assert "prompt" not in rendered
