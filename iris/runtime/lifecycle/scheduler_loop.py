"""Cancellable scheduler lifecycle loop."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Protocol

from loguru import logger

from iris.core.datetime_utils import now_utc

if TYPE_CHECKING:
    from datetime import datetime
    from types import TracebackType


class SchedulerLoopRunner(Protocol):
    """Minimal runner contract used by the scheduler lifecycle loop."""

    async def run_once(self, now: datetime) -> object:
        """Run one scheduler tick."""


async def run_scheduler_loop(
    runner: SchedulerLoopRunner,
    *,
    interval_seconds: float,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Run SchedulerRunner periodically until cancelled or stopped."""
    while stop_event is None or not stop_event.is_set():
        with _LogSchedulerRunFailure():
            await runner.run_once(now_utc())
        try:
            if stop_event is None:
                await asyncio.sleep(interval_seconds)
            else:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            continue


class _LogSchedulerRunFailure:
    """Log scheduler run failures without ending the lifecycle loop."""

    def __enter__(self) -> None:
        return None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        _ = exc_type, traceback
        if exc is None:
            return False
        if not isinstance(exc, Exception):
            return False
        logger.exception("scheduler loop run_once failed")
        return True
