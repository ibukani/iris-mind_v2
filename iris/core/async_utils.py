"""非同期実行の低レベル補助関数。"""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


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

    Raises:
        RuntimeError: スレッド内部で例外が発生した場合。元の例外情報は
            標準エラー出力に出力される（``threading.Thread`` の既定動作）。
    """
    done = asyncio.Event()
    result_box: list[R] = []

    def _target() -> None:
        try:
            result_box.append(func(*args, **kwargs))
        finally:
            done.set()

    thread = threading.Thread(target=_target, name="iris-sync-worker")
    thread.start()
    await done.wait()
    if not result_box:
        msg = f"Thread for {func.__qualname__} failed"
        raise RuntimeError(msg)
    return result_box[0]
