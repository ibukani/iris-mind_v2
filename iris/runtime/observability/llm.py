"""Runtime trace context aware LLM request observer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from iris.adapters.llm.lifecycle import ModelLoadState
from iris.adapters.llm.observability import LLMRequestObserver
from iris.runtime.observability.context import (
    increment_trace_call,
    trace_counter_extra,
    trace_extra,
)
from iris.runtime.observability.logger import LoguruRuntimeLogger
from iris.runtime.observability.ports import (
    RuntimeLatencyBudget,
    RuntimeLatencyStage,
    RuntimeModelCallKind,
)

if TYPE_CHECKING:
    from iris.runtime.observability.ports import RuntimeLogFields, RuntimeLogger


class RuntimeLLMRequestObserver(LLMRequestObserver):
    """LLM request lifecycle を runtime trace context 付きで記録する observer。"""

    def __init__(
        self,
        runtime_logger: RuntimeLogger | None = None,
        latency_budget: RuntimeLatencyBudget | None = None,
    ) -> None:
        """Observer を生成する。

        Args:
            runtime_logger: event 出力先。省略時は Loguru runtime logger。
            latency_budget: LLM generate slow warning 判定 budget。省略時は既定値。
        """
        self._logger = runtime_logger or LoguruRuntimeLogger()
        self._latency_budget = latency_budget or RuntimeLatencyBudget()

    @override
    def on_request_start(
        self,
        *,
        model: str,
        model_load_state: ModelLoadState = ModelLoadState.UNKNOWN,
    ) -> None:
        """LLM request start event を記録する。"""
        increment_trace_call(RuntimeModelCallKind.LLM_GENERATE)
        self._logger.debug(
            "llm.request.start",
            model=model,
            model_load_state=model_load_state.value,
            **trace_counter_extra(),
        )

    @override
    def on_request_success(
        self,
        *,
        model: str,
        latency_ms: float,
        finish_reason: str,
        model_load_state: ModelLoadState = ModelLoadState.UNKNOWN,
        generation_latency_ms: float | None = None,
        cold_start_latency_ms: float | None = None,
    ) -> None:
        """LLM request success event を記録する。"""
        self._logger.info(
            "llm.request.success",
            model=model,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            model_load_state=model_load_state.value,
            generation_latency_ms=generation_latency_ms,
            cold_start_latency_ms=cold_start_latency_ms,
            **trace_counter_extra(),
        )
        self._record_latency(
            model=model,
            latency_ms=latency_ms,
            model_load_state=model_load_state,
            generation_latency_ms=generation_latency_ms,
            cold_start_latency_ms=cold_start_latency_ms,
        )

    @override
    def on_request_error(
        self,
        *,
        model: str,
        latency_ms: float,
        error: BaseException,
        model_load_state: ModelLoadState = ModelLoadState.UNKNOWN,
        generation_latency_ms: float | None = None,
        cold_start_latency_ms: float | None = None,
    ) -> None:
        """LLM request error event を記録する。"""
        self._logger.warning(
            "llm.request.error",
            model=model,
            latency_ms=latency_ms,
            error_type=type(error).__name__,
            model_load_state=model_load_state.value,
            generation_latency_ms=generation_latency_ms,
            cold_start_latency_ms=cold_start_latency_ms,
            **trace_counter_extra(),
        )
        self._record_latency(
            model=model,
            latency_ms=latency_ms,
            error_type=type(error).__name__,
            model_load_state=model_load_state,
            generation_latency_ms=generation_latency_ms,
            cold_start_latency_ms=cold_start_latency_ms,
        )

    def _record_latency(
        self,
        *,
        model: str,
        latency_ms: float,
        model_load_state: ModelLoadState,
        generation_latency_ms: float | None,
        cold_start_latency_ms: float | None,
        error_type: str | None = None,
    ) -> None:
        if not self._latency_budget.enabled:
            return
        budget_ms = self._latency_budget.budget_ms_for(RuntimeLatencyStage.LLM_GENERATE)
        budget_exceeded = latency_ms > budget_ms
        fields = _latency_fields(
            _LatencyFieldsInput(
                model=model,
                latency_ms=latency_ms,
                budget_ms=budget_ms,
                budget_exceeded=budget_exceeded,
                model_load_state=model_load_state,
                generation_latency_ms=generation_latency_ms,
                cold_start_latency_ms=cold_start_latency_ms,
                error_type=error_type,
            )
        )
        self._logger.info("runtime.latency.stage", **trace_extra(**fields))
        if budget_exceeded and self._latency_budget.slow_warning_enabled:
            self._logger.warning("runtime.latency.slow", **trace_extra(**fields))


@dataclass(frozen=True)
class _LatencyFieldsInput:
    """Internal input bundle for runtime LLM latency fields."""

    model: str
    latency_ms: float
    budget_ms: float
    budget_exceeded: bool
    model_load_state: ModelLoadState
    generation_latency_ms: float | None
    cold_start_latency_ms: float | None
    error_type: str | None = None


def _latency_fields(data: _LatencyFieldsInput) -> RuntimeLogFields:
    fields = trace_counter_extra()
    fields.update(
        {
            "stage": RuntimeLatencyStage.LLM_GENERATE.value,
            "model": data.model,
            "latency_ms": data.latency_ms,
            "budget_ms": data.budget_ms,
            "budget_exceeded": data.budget_exceeded,
            "model_load_state": data.model_load_state.value,
        }
    )
    if data.generation_latency_ms is not None:
        fields["generation_latency_ms"] = data.generation_latency_ms
    if data.cold_start_latency_ms is not None:
        fields["cold_start_latency_ms"] = data.cold_start_latency_ms
    if data.error_type is not None:
        fields["error_type"] = data.error_type
    return fields
