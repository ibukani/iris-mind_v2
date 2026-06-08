"""gRPC stub 呼び出し用ヘルパー。

grpc の生成 stub が同期型として型付けされているため、
await する際に ``type: ignore[misc]`` が必要になる。
ヘルパー関数内に閉じ込めることで、呼び出し側のサプレッションを不要にする。
"""

from __future__ import annotations


async def grpc_call(coro: object) -> object:
    """Grpc stub 呼び出しの coroutine を await して結果を返す。

    Args:
        coro: grpc stub メソッドの戻り値（実際には awaitable）。

    Returns:
        object: gRPC レスポンスオブジェクト。
    """
    return await coro  # type: ignore[misc]  # grpc generated stub is typed as sync
