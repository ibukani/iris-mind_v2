from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from iris.contracts.memory import MemoryQuery, MemoryRecord, MemorySearchResult


class MemoryStore(Protocol):
    def search(self, query: MemoryQuery) -> Sequence[MemorySearchResult]: ...

    def put(self, record: MemoryRecord) -> None: ...
