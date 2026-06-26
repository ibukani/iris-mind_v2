"""Runtime structured logger tests."""

from __future__ import annotations

from loguru import logger as loguru_logger

from iris.runtime.observability.context import RuntimeTraceContext, bind_trace_context
from iris.runtime.observability.logger import LoguruRuntimeLogger


def _context() -> RuntimeTraceContext:
    return RuntimeTraceContext(
        correlation_id="corr-1",
        observation_id="obs-1",
        observation_kind="actor_message",
        ingress_kind="external_client",
        adapter_id="adapter-1",
        provider="discord",
        actor_id="actor-1",
        space_id="space-1",
    )


def test_loguru_runtime_logger_includes_trace_context() -> None:
    """Logger binds current trace context to Loguru extra."""
    entries: list[tuple[str, dict[str, object]]] = []
    logger = LoguruRuntimeLogger()

    sink_id = loguru_logger.add(
        lambda message: entries.append((message.record["message"], message.record["extra"])),
    )
    try:
        with bind_trace_context(_context()):
            logger.info("runtime.test", route="cognitive")
    finally:
        loguru_logger.remove(sink_id)

    assert entries == [
        (
            "runtime.test",
            {
                "correlation_id": "corr-1",
                "observation_kind": "actor_message",
                "ingress_kind": "external_client",
                "observation_id": "obs-1",
                "adapter_id": "adapter-1",
                "provider": "discord",
                "actor_id": "actor-1",
                "space_id": "space-1",
                "route": "cognitive",
            },
        ),
    ]


def test_loguru_runtime_logger_drops_sensitive_fields() -> None:
    """Logger drops fields that could carry text, prompts, or secrets."""
    entries: list[dict[str, object]] = []
    logger = LoguruRuntimeLogger()
    hidden_value = "hidden"

    sink_id = loguru_logger.add(lambda message: entries.append(message.record["extra"]))
    try:
        logger.info(
            "runtime.test",
            prompt_text=hidden_value,
            user_text=hidden_value,
            api_key=hidden_value,
            raw_response_body=hidden_value,
            access_token=hidden_value,
            auth_token=hidden_value,
            route="cognitive",
        )
    finally:
        loguru_logger.remove(sink_id)

    assert entries == [{"route": "cognitive"}]


def test_loguru_runtime_logger_keeps_safe_diagnostic_fields() -> None:
    """Logger keeps safe diagnostic fields with non-sensitive names."""
    entries: list[dict[str, object]] = []
    logger = LoguruRuntimeLogger()

    sink_id = loguru_logger.add(lambda message: entries.append(message.record["extra"]))
    try:
        logger.info(
            "runtime.test",
            memory_result_count=3,
            context_assembled=True,
            content_type="status",
            output_present=False,
            route="cognitive",
        )
    finally:
        loguru_logger.remove(sink_id)

    assert entries == [
        {
            "memory_result_count": 3,
            "context_assembled": True,
            "content_type": "status",
            "output_present": False,
            "route": "cognitive",
        },
    ]
