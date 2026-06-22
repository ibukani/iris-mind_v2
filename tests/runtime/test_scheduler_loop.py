"""Scheduler lifecycle loop tests."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from iris.runtime.lifecycle.scheduler_loop import run_scheduler_loop

if TYPE_CHECKING:
    from datetime import datetime

pytestmark = pytest.mark.anyio


class _FlakyRunner:
    """Runner that fails once then stops the lifecycle loop."""

    def __init__(self, stop_event: asyncio.Event) -> None:
        """Initialize fake runner."""
        self._stop_event = stop_event
        self.calls = 0

    async def run_once(self, now: datetime) -> object:
        """Fail first call, stop on second call.

        Returns:
            object marker after the second call.

        Raises:
            RuntimeError: first call only.
        """
        _ = now
        self.calls += 1
        if self.calls == 1:
            msg = "temporary scheduler failure"
            raise RuntimeError(msg)
        self._stop_event.set()
        return object()


async def test_run_scheduler_loop_logs_failure_and_continues() -> None:
    """run_scheduler_loop continues after non-cancellation runner failure."""
    stop_event = asyncio.Event()
    runner = _FlakyRunner(stop_event)

    await run_scheduler_loop(runner, interval_seconds=0.001, stop_event=stop_event)

    assert runner.calls == 2
