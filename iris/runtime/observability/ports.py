"""Runtime observability ports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from iris.runtime.observability.context import RuntimeLogValue


class RuntimeObservationObserver(Protocol):
    """IrisRuntimeService の observation lifecycle を観測する port。"""

    def record(self, event: str, **fields: RuntimeLogValue) -> None:
        """Observation lifecycle event を記録する。"""


class RuntimeLogger(Protocol):
    """Runtime code が依存する構造化ログ port。"""

    def debug(self, event: str, **fields: RuntimeLogValue) -> None:
        """DEBUG level の runtime event を記録する。"""

    def info(self, event: str, **fields: RuntimeLogValue) -> None:
        """INFO level の runtime event を記録する。"""

    def warning(self, event: str, **fields: RuntimeLogValue) -> None:
        """WARNING level の runtime event を記録する。"""

    def error(self, event: str, **fields: RuntimeLogValue) -> None:
        """ERROR level の runtime event を記録する。"""
