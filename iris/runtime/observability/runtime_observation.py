"""Runtime observation lifecycle の event と latency 計測境界。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.runtime.observability.context import trace_counter_extra, trace_extra
from iris.runtime.observability.timing import RuntimeLatencyRecorder, latency_ms

if TYPE_CHECKING:
    from iris.runtime.observability.ports import (
        RuntimeLatencyBudget,
        RuntimeLatencyStage,
        RuntimeLogValue,
        RuntimeObservationObserver,
    )


class RuntimeObservationTelemetry:
    """Observation lifecycle event と stage latency を一貫して記録する。"""

    def __init__(
        self,
        observer: RuntimeObservationObserver | None,
        latency_budget: RuntimeLatencyBudget | None,
    ) -> None:
        """Observer と optional latency budget を束ねる。"""
        self._observer = observer
        self._latency_recorder = RuntimeLatencyRecorder(observer, latency_budget)

    def record_stage(
        self,
        stage: RuntimeLatencyStage,
        started_at: float,
        *,
        route: str | None = None,
        output_present: bool | None = None,
        error_type: str | None = None,
    ) -> None:
        """Stage latency を optional observer へ渡す。"""
        self._latency_recorder.record_stage(
            stage,
            latency_ms=latency_ms(started_at),
            route=route,
            output_present=output_present,
            error_type=error_type,
        )

    def record(self, event: str, **fields: RuntimeLogValue) -> None:
        """Trace context を付加して runtime event を記録する。"""
        if self._observer is None:
            return
        merged_fields = trace_counter_extra()
        merged_fields.update(fields)
        self._observer.record(event, **trace_extra(**merged_fields))
