"""Runtime request scope trace context."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.runtime.observability.ports import (
    RuntimeLogFields,
    RuntimeLogValue,
    RuntimeModelCallKind,
)

if TYPE_CHECKING:
    from collections.abc import Generator


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


@dataclass(frozen=True)
class RuntimeTraceCounterSnapshot:
    """Runtime trace scope のモデル・分類器系 call count snapshot。"""

    model_call_count: int = 0
    classifier_call_count: int = 0
    embedding_call_count: int = 0
    reranker_call_count: int = 0


@dataclass
class _RuntimeTraceCounters:
    llm_generate: int = 0
    classifier: int = 0
    embedding: int = 0
    reranker: int = 0

    def increment(self, kind: RuntimeModelCallKind) -> None:
        if kind is RuntimeModelCallKind.LLM_GENERATE:
            self.llm_generate += 1
        elif kind is RuntimeModelCallKind.CLASSIFIER:
            self.classifier += 1
        elif kind is RuntimeModelCallKind.EMBEDDING:
            self.embedding += 1
        else:
            self.reranker += 1

    def snapshot(self) -> RuntimeTraceCounterSnapshot:
        return RuntimeTraceCounterSnapshot(
            model_call_count=self.llm_generate,
            classifier_call_count=self.classifier,
            embedding_call_count=self.embedding,
            reranker_call_count=self.reranker,
        )


_CURRENT_TRACE_CONTEXT: ContextVar[RuntimeTraceContext | None] = ContextVar(
    "iris_runtime_trace_context",
    default=None,
)
_CURRENT_TRACE_COUNTERS: ContextVar[_RuntimeTraceCounters | None] = ContextVar(
    "iris_runtime_trace_counters",
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
    """現在の async context に trace context と call counter を一時的に束縛する。"""
    context_token = _CURRENT_TRACE_CONTEXT.set(context)
    counters_token = _CURRENT_TRACE_COUNTERS.set(_RuntimeTraceCounters())
    try:
        yield
    finally:
        _CURRENT_TRACE_COUNTERS.reset(counters_token)
        _CURRENT_TRACE_CONTEXT.reset(context_token)


def increment_trace_call(kind: RuntimeModelCallKind) -> None:
    """現在の trace scope の call counter を進める。

    Trace context がない場所では no-op にする。
    """
    counters = _CURRENT_TRACE_COUNTERS.get()
    if counters is not None:
        counters.increment(kind)


def current_trace_counter_snapshot() -> RuntimeTraceCounterSnapshot:
    """現在の trace scope の call counter snapshot を返す。

    Returns:
        未束縛時は全 count 0 の snapshot。
    """
    counters = _CURRENT_TRACE_COUNTERS.get()
    if counters is None:
        return RuntimeTraceCounterSnapshot()
    return counters.snapshot()


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


def trace_counter_extra() -> RuntimeLogFields:
    """現在の trace call counter を log field として返す。

    Returns:
        structured log に含められる call counter 群。
    """
    counters = current_trace_counter_snapshot()
    return {
        "model_call_count": counters.model_call_count,
        "classifier_call_count": counters.classifier_call_count,
        "embedding_call_count": counters.embedding_call_count,
        "reranker_call_count": counters.reranker_call_count,
    }


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
