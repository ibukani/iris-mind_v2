"""キャンセル可能なバックグラウンドジョブループ。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Protocol

from loguru import logger

if TYPE_CHECKING:
    from types import TracebackType


class BackgroundJobLoopRunner(Protocol):
    """ライフサイクルループが要求する最小 runner 契約。"""

    async def run_once(self) -> object:
        """Due job を1 batch処理する。"""
        ...


async def run_background_job_loop(
    runner: BackgroundJobLoopRunner,
    *,
    interval_seconds: float,
    stop_event: asyncio.Event | None = None,
) -> None:
    """キャンセルまたは停止通知まで runner を定期実行する。"""
    while stop_event is None or not stop_event.is_set():
        with _LogBackgroundJobRunFailure():
            await runner.run_once()
        try:
            if stop_event is None:
                await asyncio.sleep(interval_seconds)
            else:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            continue


class _LogBackgroundJobRunFailure:
    """ループ外へ伝播させず runner 障害を記録する。"""

    def __enter__(self) -> None:
        return None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        _ = exc_type, traceback
        if exc is None or not isinstance(exc, Exception):
            return False
        logger.exception("background job loop run_once failed")
        return True
