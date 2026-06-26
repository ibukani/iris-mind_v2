"""Runtime trace context aware LLM request observer."""

from __future__ import annotations

from typing import override

from iris.adapters.llm.observability import LLMRequestObserver
from iris.runtime.observability.logger import LoguruRuntimeLogger, RuntimeLogger


class RuntimeLLMRequestObserver(LLMRequestObserver):
    """LLM request lifecycle を runtime trace context 付きで記録する observer。"""

    def __init__(self, runtime_logger: RuntimeLogger | None = None) -> None:
        """Observer を生成する。

        Args:
            runtime_logger: event 出力先。省略時は Loguru runtime logger。
        """
        self._logger = runtime_logger or LoguruRuntimeLogger()

    @override
    def on_request_start(self, *, model: str) -> None:
        """LLM request start event を記録する。"""
        self._logger.debug("llm.request.start", model=model)

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
        )

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
        )
