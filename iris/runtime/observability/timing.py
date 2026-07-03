"""Runtime latency event recording helpers."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from iris.runtime.observability.context import trace_counter_extra, trace_extra
from iris.runtime.observability.ports import RuntimeLatencyBudget, RuntimeLatencyStage

if TYPE_CHECKING:
    from iris.runtime.observability.ports import (
        RuntimeLogFields,
        RuntimeLogValue,
        RuntimeObservationObserver,
    )


class RuntimeLatencyRecorder:
    """Runtime response path の段階別 latency event を記録する。"""

    def __init__(
        self,
        observer: RuntimeObservationObserver | None,
        budget: RuntimeLatencyBudget | None = None,
    ) -> None:
        """Observer と budget を注入する。

        Args:
            observer: event 出力先。None の場合は no-op。
            budget: slow warning 判定 budget。None の場合は既定値。
        """
        self._observer = observer
        self._budget = budget or RuntimeLatencyBudget()

    def record_stage(
        self,
        stage: RuntimeLatencyStage,
        *,
        latency_ms: float,
        route: str | None = None,
        output_present: bool | None = None,
        error_type: str | None = None,
    ) -> None:
        """Stage latency sample と必要な slow warning を記録する。"""
        if self._observer is None or not self._budget.enabled:
            return
        budget_ms = self._budget.budget_ms_for(stage)
        budget_exceeded = latency_ms > budget_ms
        fields = _latency_fields(
            stage,
            latency_ms=latency_ms,
            budget_ms=budget_ms,
            route=route,
            output_present=output_present,
            error_type=error_type,
        )
        self._observer.record("runtime.latency.stage", **trace_extra(**fields))
        if budget_exceeded and self._budget.slow_warning_enabled:
            self._observer.record("runtime.latency.slow", **trace_extra(**fields))


def perf_counter() -> float:
    """Latency 計測用の monotonic counter を返す。

    Returns:
        ``time.perf_counter`` の現在値。
    """
    return time.perf_counter()


def latency_ms(started_at: float) -> float:
    """開始時刻からの経過時間をミリ秒で返す。

    Returns:
        経過時間ミリ秒。
    """
    return (time.perf_counter() - started_at) * 1000.0


def _latency_fields(
    stage: RuntimeLatencyStage,
    *,
    latency_ms: float,
    budget_ms: float,
    route: str | None,
    output_present: bool | None,
    error_type: str | None,
) -> RuntimeLogFields:
    fields = trace_counter_extra()
    fields.update(
        {
            "stage": stage.value,
            "latency_ms": latency_ms,
            "budget_ms": budget_ms,
            "budget_exceeded": latency_ms > budget_ms,
        }
    )
    _add_optional(fields, "route", route)
    _add_optional(fields, "output_present", output_present)
    _add_optional(fields, "error_type", error_type)
    return fields


def _add_optional(fields: RuntimeLogFields, key: str, value: RuntimeLogValue) -> None:
    if value is not None:
        fields[key] = value
