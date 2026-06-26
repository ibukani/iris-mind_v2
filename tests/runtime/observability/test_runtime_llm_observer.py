"""Runtime LLM request observer tests."""

from __future__ import annotations

from typing import override

from loguru import logger as loguru_logger
import pytest

from iris.adapters.llm.observability import ObservableLLMClient
from iris.adapters.llm.ports import LLMClient, LLMMessage, LLMRequest, LLMResponse, LLMRole
from iris.runtime.observability.context import RuntimeTraceContext, bind_trace_context
from iris.runtime.observability.llm import RuntimeLLMRequestObserver
from iris.runtime.observability.logger import LoguruRuntimeLogger


class _RecordingRuntimeLogger:
    """Runtime logger fake that records events."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, object]]] = []

    def debug(self, event: str, **fields: object) -> None:
        self.events.append(("debug", event, fields))

    def info(self, event: str, **fields: object) -> None:
        self.events.append(("info", event, fields))

    def warning(self, event: str, **fields: object) -> None:
        self.events.append(("warning", event, fields))

    def error(self, event: str, **fields: object) -> None:
        self.events.append(("error", event, fields))


class _SuccessClient(LLMClient):
    """LLM client fake returning a fixed response."""

    @override
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Return fixed response."""
        return LLMResponse(text="ok", model=request.model, finish_reason="stop")


class _ErrorClient(LLMClient):
    """LLM client fake raising a fixed error."""

    @override
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Raise fixed error.

        Raises:
            _LLMTestError: Always raised by this fake client.
        """
        del request
        raise _LLMTestError(_LLM_ERROR_MESSAGE)


class _LLMTestError(RuntimeError):
    """LLM test error."""


_LLM_ERROR_MESSAGE = "secret prompt should not appear"


def _request() -> LLMRequest:
    return LLMRequest(
        model="model-a",
        messages=(LLMMessage(role=LLMRole.USER, content="sensitive user text"),),
    )


def _context() -> RuntimeTraceContext:
    return RuntimeTraceContext(
        correlation_id="corr-1",
        observation_id="obs-1",
        observation_kind="actor_message",
        ingress_kind="trusted_adapter",
        adapter_id="adapter-1",
        provider="discord",
        actor_id="actor-1",
        space_id="space-1",
        request_started_at=2.0,
    )


@pytest.mark.anyio
async def test_llm_logs_include_correlation_id_inside_bound_context() -> None:
    """LLM logs include correlation_id when runtime trace context is bound."""
    entries: list[dict[str, object]] = []
    sink_id = loguru_logger.add(lambda message: entries.append(message.record["extra"]))
    client = ObservableLLMClient(
        _SuccessClient(),
        RuntimeLLMRequestObserver(LoguruRuntimeLogger()),
    )

    try:
        with bind_trace_context(_context()):
            await client.generate(_request())
    finally:
        loguru_logger.remove(sink_id)

    assert entries[0]["correlation_id"] == "corr-1"
    assert entries[1]["correlation_id"] == "corr-1"
    assert entries[1]["model"] == "model-a"
    assert entries[1]["finish_reason"] == "stop"
    assert isinstance(entries[1]["latency_ms"], float)
    assert entries[1]["latency_ms"] >= 0.0


@pytest.mark.anyio
async def test_llm_logs_work_without_runtime_trace_context() -> None:
    """LLM logs work without runtime trace context."""
    logger = _RecordingRuntimeLogger()
    client = ObservableLLMClient(_SuccessClient(), RuntimeLLMRequestObserver(logger))

    await client.generate(_request())

    assert [event for _, event, _ in logger.events] == [
        "llm.request.start",
        "llm.request.success",
    ]


@pytest.mark.anyio
async def test_llm_error_logs_error_type_and_reraises() -> None:
    """LLM error logs include error_type and re-raise the original error."""
    logger = _RecordingRuntimeLogger()
    client = ObservableLLMClient(_ErrorClient(), RuntimeLLMRequestObserver(logger))

    with pytest.raises(_LLMTestError, match="secret prompt"):
        await client.generate(_request())

    assert logger.events[-1][1] == "llm.request.error"
    assert logger.events[-1][2]["error_type"] == "_LLMTestError"
    assert isinstance(logger.events[-1][2]["latency_ms"], float)
    assert logger.events[-1][2]["latency_ms"] >= 0.0


@pytest.mark.anyio
async def test_llm_logs_do_not_include_sensitive_content() -> None:
    """LLM logs do not include prompt text or raw provider content."""
    logger = _RecordingRuntimeLogger()
    client = ObservableLLMClient(_ErrorClient(), RuntimeLLMRequestObserver(logger))

    with pytest.raises(_LLMTestError, match="secret prompt"):
        await client.generate(_request())

    rendered = repr(logger.events)
    assert "sensitive user text" not in rendered
    assert "secret prompt should not appear" not in rendered
