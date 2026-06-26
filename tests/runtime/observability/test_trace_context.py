"""Runtime trace context tests."""

from __future__ import annotations

from iris.runtime.observability.context import (
    RuntimeTraceContext,
    bind_trace_context,
    current_trace_context,
    trace_extra,
)


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
        request_started_at=12.5,
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
