"""学習イベント dispatch の冪等性ストア。"""

from __future__ import annotations

import asyncio
from typing import Protocol


class LearningDispatchStore(Protocol):
    """dispatch key を原子的に登録するストア。"""

    async def mark_if_absent(self, key: str) -> bool:
        """未登録なら登録して True、登録済みなら False を返す。"""
        ...


class InMemoryLearningDispatchStore:
    """プロセス内の原子的な学習 dispatch ストア。"""

    def __init__(self) -> None:
        """空の dispatch key 集合で初期化する。"""
        self._keys: set[str] = set()
        self._lock = asyncio.Lock()

    async def mark_if_absent(self, key: str) -> bool:
        """Dispatch key を一度だけ登録する。

        Returns:
            新規登録時は True、登録済みなら False。
        """
        async with self._lock:
            if key in self._keys:
                return False
            self._keys.add(key)
            return True
