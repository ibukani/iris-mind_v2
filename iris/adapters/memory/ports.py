"""メモリストレージアダプタ境界のポート。

contracts/memory.py で定義されたプロトコルを re-export する。
"""

from __future__ import annotations

from iris.contracts.memory import (
    MemoryId,
    MemoryQuery,
    MemoryRecord,
    MemorySearchResult,
    MemoryStore,
    MutableMemoryStore,
)

__all__ = [
    "MemoryId",
    "MemoryQuery",
    "MemoryRecord",
    "MemorySearchResult",
    "MemoryStore",
    "MutableMemoryStore",
]
