"""Model call budget observability tests."""

from __future__ import annotations

from iris.contracts.model_policy import ModelCallDescriptor, ModelCallKind, ModelCallSite
from iris.runtime.config.model_call_budget import RuntimeModelCallBudgetConfig
from iris.runtime.model_call_budget import ModelCallBudgetGate, bind_model_call_budget_scope
from iris.runtime.observability.context import (
    RuntimeTraceContext,
    bind_trace_context,
    trace_counter_extra,
)


def test_budget_denial_increments_avoided_large_llm_counter() -> None:
    """Budget gate が止めた large LLM call は avoided counter に出る。"""
    gate = ModelCallBudgetGate(RuntimeModelCallBudgetConfig())
    descriptor = ModelCallDescriptor(
        call_kind=ModelCallKind.LARGE_LLM,
        call_site=ModelCallSite.USER_RESPONSE_HOT_PATH,
        model_slot="default_chat",
        model_name="fake-llm",
    )

    with bind_trace_context(_trace_context()), bind_model_call_budget_scope():
        gate.check_and_record(descriptor)
        gate.check_and_record(descriptor)
        extra = trace_counter_extra()

    assert extra["model_call_count"] == 0
    assert extra["avoided_large_llm_call_count"] == 1


def _trace_context() -> RuntimeTraceContext:
    return RuntimeTraceContext(
        correlation_id="corr-observability",
        observation_id="obs-observability",
        observation_kind="actor_message",
        ingress_kind="external_client",
        adapter_id=None,
        provider=None,
        actor_id="actor-observability",
        space_id=None,
    )
