"""Cancellable scheduler lifecycle loop."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.runtime.scheduler.runner import SchedulerRunner


async def run_scheduler_loop(
    runner: SchedulerRunner,
    *,
    interval_seconds: float,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Run SchedulerRunner periodically until cancelled or stopped."""
    while stop_event is None or not stop_event.is_set():
        await runner.run_once(datetime.now(UTC))
        try:
            if stop_event is None:
                await asyncio.sleep(interval_seconds)
            else:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            continue
