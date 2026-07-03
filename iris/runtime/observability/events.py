"""Runtime observation lifecycle events."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from iris.runtime.observability.logger import LoguruRuntimeLogger
from iris.runtime.observability.ports import RuntimeLogger, RuntimeObservationObserver

if TYPE_CHECKING:
    from iris.runtime.observability.ports import RuntimeLogValue


class LoggingRuntimeObservationObserver(RuntimeObservationObserver):
    """RuntimeLogger へ observation lifecycle event を送る observer。"""

    def __init__(self, runtime_logger: RuntimeLogger | None = None) -> None:
        """Observer を生成する。

        Args:
            runtime_logger: event 出力先。省略時は Loguru runtime logger。
        """
        self._logger = runtime_logger or LoguruRuntimeLogger()

    @override
    def record(self, event: str, **fields: RuntimeLogValue) -> None:
        """Observation lifecycle event を記録する。"""
        if event.endswith(".error"):
            self._logger.error(event, **fields)
        else:
            self._logger.info(event, **fields)
