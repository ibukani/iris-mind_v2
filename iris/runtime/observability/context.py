"""Runtime request scope trace context."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

RuntimeLogValue = str | int | float | bool | None
RuntimeLogFields = dict[str, RuntimeLogValue]


@dataclass(frozen=True)
class RuntimeTraceContext:
    """1つの runtime request に紐づく安全な trace metadata。"""

    correlation_id: str
    observation_id: str | None
    observation_kind: str
    ingress_kind: str
    adapter_id: str | None
    provider: str | None
    actor_id: str | None
    space_id: str | None


_CURRENT_TRACE_CONTEXT: ContextVar[RuntimeTraceContext | None] = ContextVar(
    "iris_runtime_trace_context",
    default=None,
)


def current_trace_context() -> RuntimeTraceContext | None:
    """現在の async context に束縛された trace context を返す。

    Returns:
        束縛中の trace context。未束縛なら None。
    """
    return _CURRENT_TRACE_CONTEXT.get()


@contextmanager
def bind_trace_context(context: RuntimeTraceContext) -> Generator[None]:
    """現在の async context に trace context を一時的に束縛する。"""
    token = _CURRENT_TRACE_CONTEXT.set(context)
    try:
        yield
    finally:
        _CURRENT_TRACE_CONTEXT.reset(token)


def trace_extra(**extra: RuntimeLogValue) -> RuntimeLogFields:
    """現在の trace context と追加 metadata を安全な log extra として返す。

    Returns:
        Loguru extra へ渡せる metadata。
    """
    context = current_trace_context()
    fields: RuntimeLogFields = {}
    if context is not None:
        fields.update(_context_fields(context))
    fields.update(extra)
    return fields


def _context_fields(context: RuntimeTraceContext) -> RuntimeLogFields:
    fields: RuntimeLogFields = {
        "correlation_id": context.correlation_id,
        "observation_kind": context.observation_kind,
        "ingress_kind": context.ingress_kind,
    }
    _add_optional(fields, "observation_id", context.observation_id)
    _add_optional(fields, "adapter_id", context.adapter_id)
    _add_optional(fields, "provider", context.provider)
    _add_optional(fields, "actor_id", context.actor_id)
    _add_optional(fields, "space_id", context.space_id)
    return fields


def _add_optional(fields: RuntimeLogFields, key: str, value: str | None) -> None:
    if value is not None:
        fields[key] = value
