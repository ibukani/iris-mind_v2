"""Runtime trace context aware LLM request observer."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

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
    def on_request_start(self, *, model: str) -> None:
        """LLM request start event を記録する。"""
        increment_trace_call(RuntimeModelCallKind.LLM_GENERATE)
        self._logger.debug("llm.request.start", model=model, **trace_counter_extra())

    @override
    def on_request_success(
        self,
        *,
        model: str,
        latency_ms: float,
        finish_reason: str,
    ) -> None:
        """LLM request success event を記録する。"""
        self._logger.info(
            "llm.request.success",
            model=model,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            **trace_counter_extra(),
        )
        self._record_latency(model=model, latency_ms=latency_ms)

    @override
    def on_request_error(
        self,
        *,
        model: str,
        latency_ms: float,
        error: BaseException,
    ) -> None:
        """LLM request error event を記録する。"""
        self._logger.warning(
            "llm.request.error",
            model=model,
            latency_ms=latency_ms,
            error_type=type(error).__name__,
            **trace_counter_extra(),
        )
        self._record_latency(
            model=model,
            latency_ms=latency_ms,
            error_type=type(error).__name__,
        )

    def _record_latency(
        self,
        *,
        model: str,
        latency_ms: float,
        error_type: str | None = None,
    ) -> None:
        if not self._latency_budget.enabled:
            return
        budget_ms = self._latency_budget.budget_ms_for(RuntimeLatencyStage.LLM_GENERATE)
        budget_exceeded = latency_ms > budget_ms
        fields = _latency_fields(
            model=model,
            latency_ms=latency_ms,
            budget_ms=budget_ms,
            budget_exceeded=budget_exceeded,
            error_type=error_type,
        )
        self._logger.info("runtime.latency.stage", **trace_extra(**fields))
        if budget_exceeded and self._latency_budget.slow_warning_enabled:
            self._logger.warning("runtime.latency.slow", **trace_extra(**fields))


def _latency_fields(
    *,
    model: str,
    latency_ms: float,
    budget_ms: float,
    budget_exceeded: bool,
    error_type: str | None,
) -> RuntimeLogFields:
    fields = trace_counter_extra()
    fields.update(
        {
            "stage": RuntimeLatencyStage.LLM_GENERATE.value,
            "model": model,
            "latency_ms": latency_ms,
            "budget_ms": budget_ms,
            "budget_exceeded": budget_exceeded,
            "model_load_state": "unknown",
        }
    )
    if error_type is not None:
        fields["error_type"] = error_type
    return fields
