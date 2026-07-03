"""Runtime trace context tests."""

from __future__ import annotations

from iris.runtime.observability.context import (
    RuntimeTraceContext,
    bind_trace_context,
    current_trace_context,
    current_trace_counter_snapshot,
    increment_avoided_large_llm_call,
    increment_trace_call,
    trace_counter_extra,
    trace_extra,
)
from iris.runtime.observability.ports import RuntimeModelCallKind


def _context(correlation_id: str = "corr-1") -> RuntimeTraceContext:
    return RuntimeTraceContext(
        correlation_id=correlation_id,
        observation_id="obs-1",
        observation_kind="actor_message",
        ingress_kind="external_client",
        adapter_id=None,
        provider=None,
        actor_id="actor-1",
        space_id=None,
    )


def test_binding_exposes_context_inside_scope() -> None:
    """Bound context is visible inside the scope."""
    context = _context()
    with bind_trace_context(context):
        assert current_trace_context() == context


def test_context_resets_after_scope_exit() -> None:
    """Context binding is removed after the scope exits."""
    with bind_trace_context(_context()):
        assert current_trace_context() is not None

    assert current_trace_context() is None


def test_nested_scopes_restore_previous_context() -> None:
    """Nested bindings restore the previous context."""
    outer = _context("outer")
    inner = _context("inner")

    with bind_trace_context(outer):
        with bind_trace_context(inner):
            assert current_trace_context() == inner
        assert current_trace_context() == outer


def test_trace_extra_includes_correlation_id_when_bound() -> None:
    """trace_extra adds correlation_id from the bound context."""
    with bind_trace_context(_context()):
        extra = trace_extra(route="cognitive")

    assert extra["correlation_id"] == "corr-1"
    assert extra["route"] == "cognitive"


def test_trace_extra_works_without_bound_context() -> None:
    """trace_extra works when no context is bound."""
    assert trace_extra(route="cognitive") == {"route": "cognitive"}


def test_trace_extra_omits_optional_none_fields() -> None:
    """Optional trace fields with None are omitted."""
    with bind_trace_context(_context()):
        extra = trace_extra()

    assert "adapter_id" not in extra
    assert "provider" not in extra
    assert "space_id" not in extra
    assert extra["actor_id"] == "actor-1"


def test_trace_call_counters_increment_inside_bound_context() -> None:
    """Bound trace scope tracks model/classifier-like call counts."""
    with bind_trace_context(_context()):
        increment_trace_call(RuntimeModelCallKind.LLM_GENERATE)
        increment_trace_call(RuntimeModelCallKind.LLM_GENERATE)
        increment_trace_call(RuntimeModelCallKind.CLASSIFIER)
        increment_trace_call(RuntimeModelCallKind.EMBEDDING)
        increment_trace_call(RuntimeModelCallKind.RERANKER)
        snapshot = current_trace_counter_snapshot()

    assert snapshot.model_call_count == 2
    assert snapshot.classifier_call_count == 1
    assert snapshot.embedding_call_count == 1
    assert snapshot.reranker_call_count == 1
    assert snapshot.avoided_large_llm_call_count == 0


def test_avoided_large_llm_counter_increments_inside_bound_context() -> None:
    """Bound trace scope tracks avoided large LLM calls."""
    with bind_trace_context(_context()):
        increment_avoided_large_llm_call()
        snapshot = current_trace_counter_snapshot()

    assert snapshot.avoided_large_llm_call_count == 1


def test_trace_call_counters_reset_after_scope_exit() -> None:
    """Trace call counters are request-local."""
    with bind_trace_context(_context()):
        increment_trace_call(RuntimeModelCallKind.LLM_GENERATE)

    assert current_trace_counter_snapshot().model_call_count == 0
    assert trace_counter_extra() == {
        "model_call_count": 0,
        "classifier_call_count": 0,
        "embedding_call_count": 0,
        "reranker_call_count": 0,
        "avoided_large_llm_call_count": 0,
    }
