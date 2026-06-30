"""Background job lifecycle loop tests."""

from __future__ import annotations

import asyncio

import pytest

from iris.runtime.lifecycle.background_job_loop import run_background_job_loop

pytestmark = pytest.mark.anyio


class _FlakyRunner:
    def __init__(self, stop_event: asyncio.Event) -> None:
        self._stop_event = stop_event
        self.calls = 0

    async def run_once(self) -> object:
        self.calls += 1
        if self.calls == 1:
            message = "temporary background failure"
            raise RuntimeError(message)
        self._stop_event.set()
        return object()


async def test_background_job_loop_survives_exception_and_stops() -> None:
    """Runner 障害後もループを継続し、停止通知を処理する。"""
    stop_event = asyncio.Event()
    runner = _FlakyRunner(stop_event)
    await run_background_job_loop(runner, interval_seconds=0.001, stop_event=stop_event)
    assert runner.calls == 2


async def test_background_job_loop_is_cancellable() -> None:
    """Lifecycle task は cancellation を伝播して終了する。"""
    task = asyncio.create_task(
        run_background_job_loop(_FlakyRunner(asyncio.Event()), interval_seconds=10.0)
    )
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
