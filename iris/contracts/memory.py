from __future__ import annotations

from dataclasses import dataclass
from typing import NewType

from iris.core.ids import UserId

MemoryId = NewType("MemoryId", str)


@dataclass(frozen=True)
class MemoryRecord:
    id: MemoryId
    text: str
    subject_id: UserId | None = None
    salience: float = 0.0


@dataclass(frozen=True)
class MemoryQuery:
    text: str
    subject_id: UserId | None = None
    limit: int = 5


@dataclass(frozen=True)
class MemorySearchResult:
    record: MemoryRecord
    score: float
