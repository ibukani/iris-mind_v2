"""Issue #87 unavailable fail-fast runtime observability regression tests."""

from __future__ import annotations

from typing import override

import pytest

from iris.adapters.llm.diagnostics import LLMProviderModelUnavailableError
from iris.adapters.llm.lifecycle import ModelLifecycleSnapshot, ModelLoadState
from iris.adapters.llm.observability import ObservableLLMClient
from iris.adapters.llm.ports import LLMClient, LLMMessage, LLMRequest, LLMResponse, LLMRole
from iris.runtime.observability.context import RuntimeTraceContext, bind_trace_context
from iris.runtime.observability.llm import RuntimeLLMRequestObserver


class _RecordingRuntimeLogger:
    """Runtime logger fake that records events."""

    def __init__(self) -> None:
        """Initialize the event list."""
        self.events: list[tuple[str, str, dict[str, object]]] = []

    def debug(self, event: str, **fields: object) -> None:
        """Record a debug event."""
        self.events.append(("debug", event, fields))

    def info(self, event: str, **fields: object) -> None:
        """Record an info event."""
        self.events.append(("info", event, fields))

    def warning(self, event: str, **fields: object) -> None:
        """Record a warning event."""
        self.events.append(("warning", event, fields))

    def error(self, event: str, **fields: object) -> None:
        """Record an error event."""
        self.events.append(("error", event, fields))


class _UnusedSuccessClient(LLMClient):
    """LLM client fake that must not be called in the fail-fast path."""

    @override
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Fail if the unavailable path reaches provider generation."""
        message = f"unexpected provider call for {request.model}"
        raise AssertionError(message)


class _UnavailableProbe:
    """Lifecycle probe fake returning an unavailable model state."""

    async def snapshot(self, model: str) -> ModelLifecycleSnapshot:
        """Return an unavailable snapshot for the requested model."""
        return ModelLifecycleSnapshot(
            provider="ollama",
            model=model,
            load_state=ModelLoadState.UNAVAILABLE,
            reason="model_not_installed",
        )


def _request() -> LLMRequest:
    """Build a minimal LLM request."""
    return LLMRequest(
        model="model-a",
        messages=(LLMMessage(role=LLMRole.USER, content="hello"),),
    )


def _context() -> RuntimeTraceContext:
    """Build a trace context for model call accounting."""
    return RuntimeTraceContext(
        correlation_id="corr-1",
        observation_id="obs-1",
        observation_kind="actor_message",
        ingress_kind="trusted_adapter",
        adapter_id="adapter-1",
        provider="discord",
        actor_id="actor-1",
        space_id="space-1",
    )


@pytest.mark.anyio
async def test_unavailable_fail_fast_records_start_counter_and_latency() -> None:
    """Unavailable fail-fast is counted as an LLM generation attempt."""
    logger = _RecordingRuntimeLogger()
    client = ObservableLLMClient(
        _UnusedSuccessClient(),
        RuntimeLLMRequestObserver(logger),
        lifecycle_probe=_UnavailableProbe(),
    )

    with bind_trace_context(_context()), pytest.raises(LLMProviderModelUnavailableError):
        await client.generate(_request())

    assert [event for _, event, _ in logger.events] == [
        "llm.request.start",
        "llm.request.error",
        "runtime.latency.stage",
    ]
    start_event = logger.events[0]
    assert start_event[2]["model_load_state"] == "unavailable"
    assert start_event[2]["model_call_count"] == 1
    error_event = logger.events[1]
    assert error_event[2]["model_load_state"] == "unavailable"
    latency_event = logger.events[2]
    assert latency_event[2]["model_load_state"] == "unavailable"
    assert latency_event[2]["model_call_count"] == 1
