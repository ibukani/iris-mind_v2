"""非同期実行の低レベル補助関数。"""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType


async def run_sync_in_thread[R, **P](
    func: Callable[P, R],
    *args: P.args,
    **kwargs: P.kwargs,
) -> R:
    """同期関数を専用threadで実行し、event loopへ結果を返す。

    Args:
        func: 実行する同期関数。
        *args: 同期関数の位置引数。
        **kwargs: 同期関数のキーワード引数。

    Returns:
        同期関数の戻り値。

    同期関数が例外を送出した場合は、元の例外型とメッセージを保持して
    await元へ伝搬する。
    """
    loop = asyncio.get_running_loop()
    future: asyncio.Future[R] = loop.create_future()

    def _target() -> None:
        exception_seen = False
        result_box: list[R] = []

        class _WorkerExceptionSink:
            def __enter__(self) -> None:
                return None

            def __exit__(
                self,
                exc_type: type[BaseException] | None,
                exc: BaseException | None,
                traceback: TracebackType | None,
            ) -> bool:
                _ = exc_type, traceback
                nonlocal exception_seen
                if exc is None:
                    return False
                exception_seen = True
                loop.call_soon_threadsafe(future.set_exception, exc)
                return True

        with _WorkerExceptionSink():
            result_box.append(func(*args, **kwargs))

        if exception_seen:
            return
        loop.call_soon_threadsafe(future.set_result, result_box[0])

    thread = threading.Thread(target=_target, name="iris-sync-worker", daemon=True)
    thread.start()
    return await future
