"""async_utils helper tests."""

from __future__ import annotations

import asyncio
import threading

import pytest

from iris.core.async_utils import run_sync_in_thread

pytestmark = pytest.mark.anyio


async def test_run_sync_in_thread_returns_result() -> None:
    """run_sync_in_thread returns sync function result."""
    result = await run_sync_in_thread(lambda: 123)

    assert result == 123


async def test_run_sync_in_thread_passes_args_and_kwargs() -> None:
    """run_sync_in_thread passes positional and keyword arguments."""

    def combine(prefix: str, value: int, *, suffix: str) -> str:
        return f"{prefix}-{value}-{suffix}"

    result = await run_sync_in_thread(combine, "item", 7, suffix="done")

    assert result == "item-7-done"


async def test_run_sync_in_thread_propagates_original_exception() -> None:
    """run_sync_in_thread propagates original exception type and message."""

    class CustomError(RuntimeError):
        """Custom exception for propagation test."""

    def raise_error() -> None:
        msg = "boom"
        raise CustomError(msg)

    with pytest.raises(CustomError, match="boom"):
        await run_sync_in_thread(raise_error)


async def test_run_sync_in_thread_does_not_block_event_loop() -> None:
    """run_sync_in_thread keeps event loop available while worker runs."""
    worker_can_finish = threading.Event()

    def wait_for_signal() -> str:
        worker_can_finish.wait(timeout=1.0)
        return "done"

    task = asyncio.create_task(run_sync_in_thread(wait_for_signal))
    await asyncio.sleep(0)

    marker = False

    async def mark_loop_progress() -> None:
        nonlocal marker
        await asyncio.sleep(0)
        marker = True

    await mark_loop_progress()
    worker_can_finish.set()

    assert marker is True
    assert await task == "done"
