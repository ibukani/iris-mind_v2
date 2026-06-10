"""相互作用スペース関連のアダプタ。"""

from __future__ import annotations

from iris.adapters.spaces.memory import InMemorySpaceBindingStore
from iris.adapters.spaces.sqlite import SQLiteSpaceBindingStore

__all__ = ["InMemorySpaceBindingStore", "SQLiteSpaceBindingStore"]
