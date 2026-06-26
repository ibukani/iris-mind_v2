"""Runtime observability ports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from iris.runtime.observability.context import RuntimeLogValue


class RuntimeObservationObserver(Protocol):
    """IrisRuntimeService の observation lifecycle を観測する port。"""

    def record(self, event: str, **fields: RuntimeLogValue) -> None:
        """Observation lifecycle event を記録する。"""
